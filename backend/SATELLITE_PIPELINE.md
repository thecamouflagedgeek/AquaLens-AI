# Location-driven satellite monitoring (Sentinel-2 / Google Earth Engine)

This subsystem retrieves **monthly Sentinel-2 surface-water observations for any
location**, independent of river, country or station registry. Ganga is a validation
case, not an implementation detail: nothing in the code knows about Ganga.

It is deliberately separate from the camera pipeline. Satellite values never enter
`feature_vectors`, the 20-feature ML contract, the anomaly detector, or the Water Health
Score. Laboratory/ground measurements remain a third, separate stream.

---

## 1. What is implemented

| Component | File |
|---|---|
| AOI geometry, validation, buffering, stable key | `backend/app/satellite/aoi.py` |
| SCL masking, NDWI, monthly aggregation (reference implementation) | `backend/app/satellite/indices.py` |
| Earth Engine client (lazy init, ADC or service account) | `backend/app/satellite/gee.py` |
| Orchestration, incremental fetch, persisted jobs | `backend/app/satellite/service.py` |
| ORM models | `backend/app/satellite/models.py` |
| Additive table creation | `backend/app/satellite/schema.py` |
| HTTP API | `backend/app/api/satellite.py` |
| Dashboard panel | `frontend/src/platform/india/SatelliteHistory.jsx` |

- **Collection:** `COPERNICUS/S2_SR_HARMONIZED` (Sentinel-2 Level-2A surface reflectance)
- **Index:** `NDWI = (B3 - B8) / (B3 + B8)` — green B3, NIR B8, both native 10 m
- **Cloud masking:** SCL classes `0, 1, 3, 8, 9, 10, 11` excluded per pixel (no data,
  saturated/defective, cloud shadow, cloud medium, cloud high, thin cirrus, snow/ice)
- **Aggregation:** per-pixel **median** NDWI across the month's valid scenes, then AOI
  statistics. Water area = `sum(pixelArea)` where `NDWI >= threshold`, on a fixed 10 m grid
- **Algorithm version:** `s2-sr-ndwi-monthly` `1.0.0`

## 2. Install the dependency

Windows PowerShell, from the repository root, with the backend virtual environment
active:

```powershell
python -m pip install -r backend/requirements.txt
```

This adds `earthengine-api` and `google-auth`. If Earth Engine is not installed the rest
of the application still runs; only satellite retrieval is unavailable and the API says so.

## 3. Google Cloud project configuration

1. Create or select a Google Cloud project.
2. Enable the **Earth Engine API** for that project.
3. Register the project for Earth Engine access (Earth Engine requires the account to be
   authorised, not just the API to be enabled).
4. Note the project id — that is `GEE_PROJECT_ID`.

## 4. Authentication

### 4a. Local developer authentication (OAuth, run once by a human)

```powershell
earthengine authenticate
```

This opens a browser and writes a refresh token to your user profile. It is an
**interactive, per-developer** step. The backend never calls `ee.Authenticate()`: server
startup must not prompt.

### 4b. Service account (unattended backend)

1. Create a service account in the same project and grant it Earth Engine access.
2. Download its JSON key and store it **outside this repository**, e.g.
   `$env:USERPROFILE\secrets\aqualens-gee.json`.
3. Point the environment variable at the **path**, never the key contents:

```powershell
$env:GOOGLE_APPLICATION_CREDENTIALS = "$env:USERPROFILE\secrets\aqualens-gee.json"
```

Application Default Credentials also work on GCP (workload identity / attached service
account) with `GOOGLE_APPLICATION_CREDENTIALS` left blank.

Never commit a key, a token, or a populated `.env`. `.env` is not tracked.

## 5. Backend environment variables

Create `backend/.env` (or `.env` at the repository root — `core/config.py` reads the root
path) from `.env.example` and set:

```
GEE_PROJECT_ID="your-earth-engine-project-id"
GOOGLE_APPLICATION_CREDENTIALS=""          # blank when using earthengine authenticate
SATELLITE_COLLECTION="COPERNICUS/S2_SR_HARMONIZED"
SATELLITE_DEFAULT_BUFFER_M=300
SATELLITE_DEFAULT_MONTHS=24
```

The dashboards never receive credentials. No `VITE_*` variable is involved.

## 6. Verify configuration

```powershell
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload
```

```powershell
curl.exe -s http://localhost:8000/satellite/status
```

`earth_engine.project_configured`, `package_installed` and `initialised` are booleans;
`last_error` carries a message with no secret. `auth_hint` explains the next step when
authentication is missing.

## 7. Run a satellite history fetch

Sign in, then (cookie session required):

```powershell
# 1. Resolve an area of interest. A point is buffered into a polygon.
curl.exe -s -c cookies.txt -X POST http://localhost:8000/auth/login `
  -H "Content-Type: application/json" `
  -d '{\"username\":\"admin_1\",\"password\":\"<your password>\"}'

curl.exe -s -b cookies.txt -X POST http://localhost:8000/satellite/aois/resolve `
  -H "Content-Type: application/json" `
  -d '{\"name\":\"Tehri downstream\",\"latitude\":30.3719,\"longitude\":78.4777,\"buffer_m\":300}'

# 2. Queue the last 24 months (returns HTTP 202 with a job id)
curl.exe -s -b cookies.txt -X POST http://localhost:8000/satellite/aois/1/fetch `
  -H "Content-Type: application/json" -d '{\"months\":24}'

# 3. Poll the persisted job
curl.exe -s -b cookies.txt http://localhost:8000/satellite/jobs/1

# 4. Read stored monthly observations + availability
curl.exe -s -b cookies.txt "http://localhost:8000/satellite/aois/1/observations?start_month=2024-11&end_month=2026-10"
```

`30.3719, 78.4777` comes from `frontend/src/platform/india/ganga-stations.json`
("D/s of Tehri Dam") and is used **only** as a manual fixture. It is not hardcoded in the
service or the API.

In the UI: sign in as the India workspace account → select a mapped station →
**Fingerprint** → *Satellite water history (Sentinel-2)* → **Retrieve satellite history**.
Changing the selected station loads that location's already-stored series; a location that
is fully cached issues no Earth Engine work.

## 8. Verify stored observations

```powershell
python - <<'PY'
import sqlite3
con = sqlite3.connect("file:backend/aqualens.db?mode=ro", uri=True)
print(con.execute("select count(*) from satellite_aois").fetchone())
for row in con.execute("select aoi_id, month, status, ndwi_mean, water_area_km2, scene_count "
                       "from satellite_observations order by month desc limit 10"):
    print(row)
PY
```

Re-running a fetch for the same AOI, month, collection, algorithm version, threshold and
cloud filter **updates** the existing row: `UNIQUE(aoi_id, month, collection,
algorithm_version, ndwi_threshold, max_cloud_pct)` prevents duplicates. Already-stored
months are skipped unless `force: true` is passed.

## 9. API summary

| Method | Path | Purpose |
|---|---|---|
| GET | `/satellite/status` | readiness + defaults (no secrets) |
| POST | `/satellite/aois/resolve` | create/resolve AOI from point+buffer or polygon |
| GET | `/satellite/aois` | list stored AOIs |
| GET | `/satellite/aois/{id}` | AOI detail + geometry |
| GET | `/satellite/aois/{id}/observations` | stored monthly observations |
| GET | `/satellite/aois/{id}/availability` | coverage: with data / without data / not fetched |
| POST | `/satellite/aois/{id}/fetch` | queue missing months (202, background) |
| GET | `/satellite/jobs/{id}` | acquisition/processing status |

All routes require an authenticated session. They are also mounted under `/api/v1`.

## 10. Live Earth Engine smoke test

The test suite mocks Earth Engine. Before pointing the dashboard at real data, confirm that
live retrieval works for one small AOI with the dedicated smoke test. It runs the production
`aoi.build_aoi` + `gee.monthly_ndwi` code path against the real service, prints what came
back, and **writes nothing to the database** (no AOI, observation or job row).

It uses your local Earth Engine session (`earthengine authenticate`) or the service account
referenced by `GOOGLE_APPLICATION_CREDENTIALS`, and reads `GEE_PROJECT_ID` from
`backend/.env`. Credentials are never passed on the command line and never printed.

Run it from the repository root in PowerShell:

```powershell
python -m backend.scripts.smoke_gee `
  --latitude 30.3719 --longitude 78.4777 `
  --buffer-m 300 --start 2025-01
```

A range is also accepted, and `--json` emits one machine-readable object per month:

```powershell
python -m backend.scripts.smoke_gee --latitude 30.3719 --longitude 78.4777 `
  --buffer-m 300 --start 2025-01 --end 2025-03
python -m backend.scripts.smoke_gee --latitude 30.3719 --longitude 78.4777 `
  --start 2025-01 --json
```

Expected successful output for one month:

```
Live Earth Engine smoke test
  project   : your-gee-project-id
  AOI       : 30.3719, 78.4777 · 300 m buffer · 0.2827 km²
  window    : 2025-01 → 2025-01 (1 month(s))
  collection: COPERNICUS/S2_SR_HARMONIZED

2025-01  (2025-01-01 → 2025-02-01)
  status            : ok
  scenes (post-cloud): 9
  NDWI threshold    : 0.0
  NDWI mean/median  : -0.1832 / -0.1904
  water area        : 0.0412 km²
  water fraction    : 0.1459
  valid pixels      : 2754
  sensor            : S2A/S2B
  projection        : EPSG:32644
  resolution        : 10.0 m

1/1 month(s) returned a usable observation.
```

Exit codes: `0` usable observation, `1` query ran but no month had usable imagery (a data
result, not a service failure), `2` bad arguments, `3` Earth Engine not configured or not
authenticated, `4` Earth Engine rejected the query. Every non-zero exit prints an actionable
message on stderr and no result is ever invented.

## 11. Tests

```powershell
python -m pytest backend/tests/test_satellite.py -q
```

Earth Engine is mocked; no Google account or network access is required. Covered: AOI
validation and rejection, geodesic point buffering, polygon handling, stable identifiers,
SCL masking, NDWI arithmetic and scale invariance, monthly median compositing, empty and
fully-masked months, water-area pixel counting and threshold sensitivity, Earth Engine
configuration/auth failure messages, persistence, duplicate prevention, incremental
fetching, availability reporting, and API request/response handling.

## 12. Known limitations and scientific caveats

- **NDWI is not a water-quality measurement.** It indicates surface water presence. It does
  not measure dissolved oxygen, BOD, turbidity, TSS, chlorophyll or chemical contamination.
- **Water area is an estimate.** It is a pixel count at 10 m above a threshold you choose;
  it is not surveyed or bathymetric area. Threshold choice materially changes the number,
  so the threshold is stored on every record.
- **Monthly medians hide events.** A short flood or drawdown inside a month can be
  suppressed by compositing.
- **No usable imagery is not zero water.** Such months are stored with
  `status='no_scenes'` or `'no_valid_pixels'` and null measurements, plotted as gaps.
- **AOI granularity matters.** A 300 m buffer sample is not the whole river. A single point
  cannot represent a reach or a reservoir; supply a polygon for those.
- **Coverage is optical.** Persistent cloud, monsoon season and terrain shadow reduce
  usable observations; expect gaps in the record and read `availability` before drawing
  conclusions.
- **Sentinel-2 era only.** S2A launched 2015 and S2B 2017, so a 24-month window is well
  within coverage, but requests before 2015 return no scenes.
- **This is not comparable to the camera fingerprint numerically.** The two streams share
  no feature space and are never combined into one score.
- **Job execution is in-process.** Background jobs run in a daemon thread with persisted
  status. A restart cannot resume a worker thread, so on the next startup any job left
  `queued`/`running` is marked `interrupted` with an explanation and its progress counters
  intact. Retrieving the history again is incremental: stored months are skipped, so only
  the remaining months are fetched.
