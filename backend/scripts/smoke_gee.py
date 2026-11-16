"""Live Earth Engine smoke test for the Sentinel-2 NDWI path.

This is the only script that talks to the *real* Google Earth Engine service. It runs the
production query (``backend.app.satellite.gee.monthly_ndwi``, which builds the AOI through
``backend.app.satellite.aoi``) for one or more months and prints what came back.

It deliberately:

- uses the local Earth Engine session configured by the developer
  (``earthengine authenticate``) or a service account referenced by
  ``GOOGLE_APPLICATION_CREDENTIALS``;
- reads ``GEE_PROJECT_ID`` from the backend configuration / ``.env``;
- takes coordinates as ordinary arguments, never credentials;
- never prints or logs tokens, keys or credential contents;
- never writes to the database -- no AOI row, observation or job is created;
- never fabricates a fallback result: if Earth Engine is unavailable the script fails.

Usage (see backend/SATELLITE_PIPELINE.md for the documented command):

    python -m backend.scripts.smoke_gee --latitude 30.3719 --longitude 78.4777 \
        --buffer-m 300 --start 2025-01 --end 2025-03

Exit codes:
    0  every requested month returned a usable observation
    1  the query ran but no month produced usable imagery
    2  invalid arguments
    3  Earth Engine is not configured / not authenticated (see the printed hint)
    4  Earth Engine rejected or failed the query
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Dict, List, Sequence

from backend.app.core.config import settings
from backend.app.satellite import aoi as aoi_module
from backend.app.satellite import gee, indices


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="smoke_gee",
        description=(
            "Run the production Sentinel-2 NDWI query against live Google Earth Engine "
            "for one buffered point. No database rows are written."
        ),
    )
    parser.add_argument("--latitude", type=float, required=True, help="WGS84 latitude of the AOI centre.")
    parser.add_argument("--longitude", type=float, required=True, help="WGS84 longitude of the AOI centre.")
    parser.add_argument(
        "--buffer-m",
        type=float,
        default=aoi_module.DEFAULT_BUFFER_M,
        help=f"Radius of the circular AOI in metres (default {aoi_module.DEFAULT_BUFFER_M:g}).",
    )
    parser.add_argument("--start", required=True, help="First month to query, YYYY-MM.")
    parser.add_argument(
        "--end",
        default=None,
        help="Last month to query, YYYY-MM. Defaults to --start (a single month).",
    )
    parser.add_argument(
        "--ndwi-threshold",
        type=float,
        default=indices.NDWI_THRESHOLD_DEFAULT,
        help=f"NDWI water threshold (default {indices.NDWI_THRESHOLD_DEFAULT}).",
    )
    parser.add_argument(
        "--max-cloud-pct",
        type=float,
        default=indices.MAX_CLOUD_PCT_DEFAULT,
        help=f"Per-scene cloud filter (default {indices.MAX_CLOUD_PCT_DEFAULT}).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit one JSON object per month instead of the human-readable report.",
    )
    args = parser.parse_args(argv)

    if not -90.0 <= args.latitude <= 90.0:
        parser.error("--latitude must be between -90 and 90.")
    if not -180.0 <= args.longitude <= 180.0:
        parser.error("--longitude must be between -180 and 180.")
    if not 50.0 <= args.buffer_m <= 50_000.0:
        parser.error("--buffer-m must be between 50 and 50000 metres.")
    if not -1.0 <= args.ndwi_threshold <= 1.0:
        parser.error("--ndwi-threshold must be between -1 and 1.")
    if not 0.0 <= args.max_cloud_pct <= 100.0:
        parser.error("--max-cloud-pct must be between 0 and 100.")
    args.end = args.end or args.start
    return args


def _value(value: Any, digits: int = 4) -> str:
    return f"{value:.{digits}f}" if isinstance(value, (int, float)) else "—"


def _report(month: str, result: Dict[str, Any], args: argparse.Namespace) -> None:
    if args.json:
        print(json.dumps({"month": month, **result}, default=str, sort_keys=True))
        return

    print(f"\n{month}  ({result.get('period_start')} → {result.get('period_end')})")
    print(f"  status            : {result.get('status')}")
    print(f"  scenes (post-cloud): {result.get('scene_count')}")
    print(f"  NDWI threshold    : {result.get('ndwi_threshold')}")
    print(f"  NDWI mean/median  : {_value(result.get('ndwi_mean'))} / {_value(result.get('ndwi_median'))}")
    area = result.get("water_area_km2")
    print(f"  water area        : {_value(area)} km²" if area is not None else "  water area        : —")
    print(f"  water fraction    : {_value(result.get('water_fraction'))}")
    print(f"  valid pixels      : {result.get('valid_pixel_count')}")
    print(f"  sensor            : {result.get('sensor') or '—'}")
    print(f"  projection        : {result.get('projection')}")
    print(f"  resolution        : {result.get('resolution_m')} m")


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])

    # Argument problems are reported before configuration problems, so a typo never looks
    # like an authentication failure.
    try:
        months = indices.month_sequence(args.start, args.end)
    except ValueError as error:
        print(f"Invalid month range: {error}", file=sys.stderr)
        return 2

    project = (settings.GEE_PROJECT_ID or "").strip()
    if not project:
        print(
            "Earth Engine is not configured: GEE_PROJECT_ID is empty.\n"
            "Set GEE_PROJECT_ID in backend/.env to the Google Cloud project with the Earth "
            "Engine API enabled, then retry.",
            file=sys.stderr,
        )
        return 3

    try:
        spec = aoi_module.build_aoi(
            name=f"Smoke test {args.latitude:.4f}, {args.longitude:.4f}",
            latitude=args.latitude,
            longitude=args.longitude,
            buffer_m=args.buffer_m,
        )
        geometry = spec["geometry"]
    except aoi_module.AOIValidationError as error:
        print(f"AOI could not be built: {error}", file=sys.stderr)
        return 2

    print(
        "Live Earth Engine smoke test\n"
        f"  project   : {project}\n"
        f"  AOI       : {args.latitude:.4f}, {args.longitude:.4f} · {args.buffer_m:g} m buffer "
        f"· {spec['area_km2']:.4f} km²\n"
        f"  window    : {args.start} → {args.end} ({len(months)} month(s))\n"
        f"  collection: {settings.SATELLITE_COLLECTION}"
    )

    usable = 0
    failures: List[str] = []
    for month in months:
        try:
            result = gee.monthly_ndwi(
                geometry,
                month,
                ndwi_threshold=args.ndwi_threshold,
                max_cloud_pct=args.max_cloud_pct,
            )
        except gee.GeeUnavailable as error:
            print(f"\nEarth Engine is not usable: {error}", file=sys.stderr)
            return 3
        except gee.GeeQueryError as error:
            failures.append(month)
            print(f"\n{month}: query failed — {error}", file=sys.stderr)
            continue

        _report(month, result, args)
        if result.get("status") == indices.STATUS_OK:
            usable += 1

    if failures and not usable:
        print(
            "\nEarth Engine rejected the query for every requested month. "
            "Check the project has Earth Engine access and that the credentials are valid.",
            file=sys.stderr,
        )
        return 4
    if not usable:
        print(
            "\nThe query succeeded but no month produced usable imagery "
            "(no scenes, no valid pixels, or too few pixels). This is a data result, not a "
            "service failure.",
            file=sys.stderr,
        )
        return 1

    print(f"\n{usable}/{len(months)} month(s) returned a usable observation.")
    return 0


if __name__ == "__main__":  # pragma: no cover - manual live entry point
    raise SystemExit(main())
