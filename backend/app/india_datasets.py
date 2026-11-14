"""Read-only adapters for the supplied India datasets."""
import csv
import math
from functools import lru_cache
from itertools import islice
from pathlib import Path

import cv2
import numpy as np

DATA = Path(__file__).resolve().parents[2] / 'data'


def measurements(filename):
    with (DATA / filename).open(encoding='utf-8-sig', errors='replace', newline='') as stream:
        rows = csv.reader(stream)
        headers = next(rows)
        return {'source': filename, 'headers': headers, 'rows': [
            [None if value.strip().upper() in ('', 'NA', 'N/A') else value.strip() for value in row]
            for row in rows if len(row) == len(headers) and any(row)
        ]}


@lru_cache(maxsize=1)
def census_files():
    return sorted((DATA / 'First Census of water bodies in India').glob('WBC*.csv'))


def census_page(file, offset):
    path = next((p for p in census_files() if p.name == file), None)
    if path is None:
        return None
    fields = ('unique_id', 'water_body_name', 'State Name', 'District Name', 'Village Name',
              'basin_name', 'ref_water_body_type_id_name')
    with path.open(encoding='utf-8-sig', errors='replace', newline='') as stream:
        records = [{key: row.get(key) for key in fields}
                   for row in islice(csv.DictReader(stream), offset, offset + 21)]
    return {'source': path.name, 'headers': fields, 'rows': [
        [record[key] for key in fields] for record in records[:20]
    ], 'has_more': len(records) > 20}


@lru_cache(maxsize=1)
def satellite_images():
    directory = DATA / 'Water Bodies Satellite Imagery' / 'Water Bodies Dataset' / 'Images'
    return {p.name: p for p in sorted(directory.glob('water_body_*.jpg'))}


def satellite_location(name):
    manifest = DATA / 'Water Bodies Satellite Imagery' / 'locations.csv'
    if not manifest.is_file():
        return None
    with manifest.open(encoding='utf-8-sig', newline='') as stream:
        matches = [row for row in csv.DictReader(stream) if row.get('filename') == name]
    if len(matches) != 1:
        return None
    row = matches[0]
    try:
        lat, lon = float(row['latitude']), float(row['longitude'])
        source = row['source'].strip()
        if source and math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180:
            return {'latitude': lat, 'longitude': lon, 'source': source}
    except (KeyError, ValueError, TypeError, AttributeError):
        pass
    return None


@lru_cache(maxsize=128)
def satellite_features(name):
    path = satellite_images()[name]
    image = cv2.imdecode(np.frombuffer(path.read_bytes(), dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        return None
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blue, green, red = cv2.mean(image)[:3]
    return {'width': image.shape[1], 'height': image.shape[0],
            'mean_red_dn': red, 'mean_green_dn': green, 'mean_blue_dn': blue,
            'grayscale_std_dn': float(gray.std()),
            'segmentation_available': False,
            'scope': 'Whole rendered JPEG; pixel values are not surface reflectance.'}
