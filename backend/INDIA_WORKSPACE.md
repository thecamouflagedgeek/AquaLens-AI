# Indian river monitoring workspace

Only the authenticated `admin_1` account can use `/india/*`. The existing workspace's routes, station records, RF artifacts and analysis services are not replaced. Start the backend normally with `python -m uvicorn backend.app.main:app --reload --port 8000`; startup creates the additional India-only tables. The frontend uses the same configured Axios API base URL and HttpOnly cookie session.

## First monitoring workflow

1. Sign in as `admin_1` using the separately configured development account password.
2. Register a real station on Ganga, Mahanadi or Narmada. Enter its state, coordinates and coordinate provenance. Coordinates are labelled operator-registered, not independently verified by the application. No locations are seeded.
3. Record sample images with sampling time, operator-assigned season, camera, exposure/settings, illumination, preparation and a capture-protocol identifier. Mark only acquisition-checked samples as reference-eligible. Original PNG/JPEG/WebP bytes and checksums are retained. Duplicate images at the same station are rejected.
4. Select at least five distinct eligible observations from the same season and capture protocol to establish a frozen provisional reference version. Camera, camera settings, illumination and preparation must also match. More samples do not by themselves validate the method. Different acquisition settings require a different protocol.
5. Inspect the current, previous and reference images, all 20 actual RF features, per-feature histories, reference interquartile ranges and deviations. RF classification remains separate from source-relative screening; Indian-domain accuracy is not claimed. RF unavailability does not discard the original image or extracted features.
6. Add actual laboratory and contextual measurements with units, timestamps and provenance. Pair measurements to specific observations only when justified; otherwise leave them as unpaired station records. These station-level evidence tables display the full evidence register, with timestamps; date filters apply to observation comparisons and trends.
7. Create evidence-linked monitoring actions, record status changes and remarks, and download the station research report. Reports are plain-text research exports containing structured JSON evidence, not regulatory certificates.

## Method and limitations

India reference statistics use the station/season/capture-context median, Q25, Q75 and IQR for the exact existing 20-feature schema. Signed normalized deviation is `(current - reference median) / reference IQR`. A zero IQR with a nonzero departure has an undefined scale and is shown as unavailable; no arbitrary epsilon is used to manufacture a score. The overall mean absolute normalized deviation is issued only when all 20 scales are comparable. The optional Visual Stability Score is `100 * exp(-0.35 * mean_absolute_deviation)` and is explicitly exploratory. A screening threshold of 2.5 and three consecutive non-reference observations above it are heuristic flags, not validated event labels.

Reference-member observations are marked and excluded from stability-score histories. Comparisons are retrospective against the selected frozen reference version; they do not establish prospective prediction performance. A checksum proves byte identity, not independent environmental sampling. Seasonal labels do not infer rainfall, discharge, contamination or cause. RF global importances come from the loaded model, not hardcoded numbers, and do not explain an individual classification. No contamination, potability, validated forecast or Indian river health claim is inferred from an image alone.

## API

All routes require an authenticated India account; an existing-workspace account receives 403.

- `GET/POST /india/stations`
- `POST /india/stations/{id}/observations` — multipart `metadata` JSON and `image`
- `GET /india/observations/{id}/image` — authenticated original image
- `POST /india/stations/{id}/fingerprint` — explicit reference observation IDs
- `GET /india/stations/{id}/analysis?observation_id=&start=&end=` — timezone-aware observation filters; includes station evidence register
- `POST /india/stations/{id}/evidence/laboratory`
- `POST /india/stations/{id}/evidence/context`
- `POST /india/stations/{id}/actions`
- `PATCH /india/actions/{id}`
- `GET /india/stations/{id}/report?observation_id=&start=&end=`

The public OpenStreetMap tile service needs internet access. A tile failure is reported without inventing a replacement map. Three.js renders a decorative header surface, separate from measured-data charts; it is lazy-loaded, respects reduced-motion preferences and releases WebGL resources when the workspace unmounts.

Run `python -m unittest discover -s tests -v` for the isolated backend tests. Synthetic test images and station fixtures are stored only in isolated test databases and temporary folders; none are seeded in the application.

### Ganga historical archive

Open **Ganga archive**, or select **Ganga** without a local station and press **Search**. The archive serves the supplied data.gov.in 2012 response snapshot from `backend/app/ganga_2012.json`. It contains 10 of the 66 records reported by the source. No upstream connection or API key is needed. Local filters apply only to AquaLens observations.

The India map plots historical Ganga CSV locations only where the station name
matches CPCB's amended RTWQM station table. The coordinates and document link
are stored in frontend/src/platform/india/ganga-stations.json. Unmatched
stations remain selectable for measurements. Historical markers are not
AquaLens image collection stations.

To enable the optional satellite basemap, configure these in frontend/.env
and restart Vite:

    VITE_INDIA_SATELLITE_TILE_URL=https://your-provider.example/tiles/{z}/{x}/{y}.png
    VITE_INDIA_SATELLITE_LABEL=Sentinel-2 satellite imagery (2024)
    VITE_INDIA_SATELLITE_ATTRIBUTION=Your provider credit and Copernicus data year

Use a browser-accessible Web Mercator XYZ tile endpoint authorized for your
deployment, with the matching acquisition date or mosaic year in the label.
Do not place private provider credentials in VITE variables. Satellite imagery
is for map context and is not fed into the AquaLens image fingerprint pipeline.

To map a satellite JPEG, provide a verified crosswalk at
data/Water Bodies Satellite Imagery/locations.csv with columns
filename,latitude,longitude,source. Use one record per JPEG filename.
Without that crosswalk the image is shown without a location pin.

### Build a satellite fingerprint

Install rasterio in the backend environment and set NASA_EARTHDATA in
backend/.env to a current Earthdata Login token authorized for PO.DAAC.
Select a mapped station in Fingerprint or Findings, then click
Build satellite fingerprint. The backend searches the last 90 days and
caches matching B01 WTR GeoTIFFs under data/OPERA. It reports downloads,
cache hits, and access failures separately. The satellite baseline requires
five earlier usable dates on the same grid as the latest usable scene.
