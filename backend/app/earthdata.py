import json
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode
from urllib.request import urlopen

COLLECTION = 'C2617126679-POCLOUD'


def catalog(latitude, longitude):
    now = datetime.now(timezone.utc)
    dates = [d.strftime('%Y-%m-%dT%H:%M:%SZ') for d in (now - timedelta(days=90), now)]
    query = urlencode({'collection_concept_id': COLLECTION, 'point': f'{longitude},{latitude}',
                       'temporal': ','.join(dates), 'sort_key': '-start_date', 'page_size': 12})
    with urlopen('https://cmr.earthdata.nasa.gov/search/granules.json?' + query, timeout=12) as response:
        return json.load(response)['feed']['entry']


def scenes(latitude, longitude):
    return [{'id': row['id'], 'title': row['title'], 'acquired': row.get('time_start'),
             'catalog_url': 'https://cmr.earthdata.nasa.gov/search/concepts/' + row['id'] + '.html'}
            for row in catalog(latitude, longitude)]

def water_profile(latitude, longitude, paths=None):
    """Compare georeferenced B01 WTR rasters in one fixed 300 m square."""
    from pathlib import Path
    from statistics import median
    import numpy as np
    import rasterio
    from rasterio.warp import transform
    from rasterio.windows import Window

    folder = Path(__file__).resolve().parents[2] / 'data' / 'OPERA'
    rows = []
    for path in (paths if paths is not None else sorted(folder.glob('OPERA_L3_DSWx-HLS_*_B01_WTR.tif'))):
        parts = path.stem.split('_')
        try:
            date = datetime.strptime(parts[4], '%Y%m%dT%H%M%SZ')
            with rasterio.open(path) as ds:
                if not ds.crs or not ds.crs.is_projected or ds.crs.linear_units != 'metre':
                    continue
                x, y = transform('EPSG:4326', ds.crs, [longitude], [latitude])
                row, col = ds.index(x[0], y[0])
                if not (5 <= row < ds.height - 5 and 5 <= col < ds.width - 5):
                    continue
                if abs(ds.res[0] - 30) > 0.01 or abs(ds.res[1] - 30) > 0.01:
                    continue
                grid = (ds.crs.to_string(), tuple(ds.transform))
                values = ds.read(1, window=Window(col - 5, row - 5, 10, 10), masked=True).compressed()
            counts = [int(np.count_nonzero(values == cls)) for cls in (0, 1, 2)]
            valid = sum(counts)
            if valid < 80:
                continue
            rows.append({'id': path.stem, 'date': date.isoformat() + 'Z', 'tile': parts[3],
                         'grid': grid, 'valid': valid, 'open': counts[1] / valid, 'partial': counts[2] / valid})
        except (ValueError, IndexError, rasterio.errors.RasterioError):
            continue
    rows.sort(key=lambda row: row['date'], reverse=True)
    latest = rows[0] if rows else None
    seen = {latest['date'][:10]} if latest else set()
    reference = []
    for row in rows[1:]:
        day = row['date'][:10]
        if row['tile'] == latest['tile'] and row['grid'] == latest['grid'] and day not in seen:
            seen.add(day)
            reference.append(row)
    features = []
    if latest:
        for key in ('open', 'partial'):
            values = [row[key] for row in reference] if len(reference) >= 5 else []
            center = median(values) if values else None
            features.append({'name': key, 'current': latest[key], 'median': center,
                             'reference_min': min(values) if values else None,
                             'reference_max': max(values) if values else None,
                             'difference': latest[key] - center if center is not None else None})
    for row in rows:
        row.pop('grid')
    return {'latest': latest, 'reference': reference, 'features': features,
            'non_water_median': median([max(0, 1 - row['open'] - row['partial']) for row in reference]) if len(reference) >= 5 else None,
            'deviation': sum(abs(f['difference']) for f in features) / len(features)
            if features and len(reference) >= 5 else None}


def build_profile(latitude, longitude):
    import os
    import re
    import tempfile
    from concurrent.futures import ThreadPoolExecutor
    from pathlib import Path
    from urllib.parse import urlsplit
    from urllib.request import HTTPRedirectHandler, Request, build_opener

    import rasterio
    from dotenv import dotenv_values
    from .core.config import BASE_DIR

    token = (os.getenv('NASA_EARTHDATA') or dotenv_values(BASE_DIR / '.env',
             encoding='utf-8-sig').get('NASA_EARTHDATA') or '').strip()
    if not token:
        raise PermissionError('Set NASA_EARTHDATA in backend/.env.')

    class AssetRedirect(HTTPRedirectHandler):
        max_redirections = 2

        def redirect_request(self, req, fp, code, msg, headers, newurl):
            destination = urlsplit(newurl)
            if destination.scheme != 'https' or destination.netloc != 'deotb6e7tfubr.cloudfront.net':
                return None
            # PO.DAAC signs this URL; never forward the Earthdata token.
            return Request(newurl)

    folder = Path(__file__).resolve().parents[2] / 'data' / 'OPERA'
    folder.mkdir(parents=True, exist_ok=True)
    entries = catalog(latitude, longitude)
    assets = {}
    for row in entries:
        for link in row.get('links', []):
            url = link.get('href', '')
            parsed = urlsplit(url)
            name = parsed.path.rsplit('/', 1)[-1]
            if (parsed.scheme == 'https' and parsed.netloc == 'archive.podaac.earthdata.nasa.gov'
                and re.fullmatch(r'OPERA_L3_DSWx-HLS_[A-Za-z0-9_.-]+_B01_WTR[.]tif', name)):
                assets[name] = url
                break

    def fetch(item):
        name, url = item
        target = folder / name
        if target.is_file():
            return target, 'cached'
        tmp = None
        try:
            request = Request(url, headers={'Authorization': 'Bearer ' + token})
            with build_opener(AssetRedirect()).open(request, timeout=10) as response:
                with tempfile.NamedTemporaryFile(dir=folder, suffix='.part', delete=False) as out:
                    tmp = Path(out.name)
                    remaining = 32 * 1024 * 1024
                    while chunk := response.read(65536):
                        remaining -= len(chunk)
                        if remaining < 0:
                            raise ValueError('Asset exceeds size limit')
                        out.write(chunk)
            with rasterio.open(tmp) as raster:
                if raster.driver != 'GTiff' or not raster.crs:
                    raise ValueError('Expected a georeferenced GeoTIFF')
            tmp.replace(target)
            return target, 'downloaded'
        except (OSError, ValueError, rasterio.errors.RasterioError) as exc:
            return None, 'access_denied' if getattr(exc, 'code', None) in (301, 302, 303, 307, 308, 401, 403) else 'failed'
        finally:
            if tmp is not None:
                tmp.unlink(missing_ok=True)

    with ThreadPoolExecutor(max_workers=4) as pool:
        downloads = list(pool.map(fetch, assets.items()))
    statuses = [status for _, status in downloads]
    result = water_profile(latitude, longitude, [path for path, _ in downloads if path])
    return {**result, 'import': {'scenes': len(entries), 'assets': len(assets),
            **{key: statuses.count(key) for key in ('cached', 'downloaded', 'access_denied', 'failed')}}}
