"""Tests for the location-driven satellite pipeline.

Earth Engine is mocked throughout: no Google credentials and no network access are
required. Set ``AQUALENS_DATABASE`` to an isolated database path if you want the API
tests to use a file rather than an in-memory SQLite engine.
"""

from __future__ import annotations

import json
import sys
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.app.db.session import Base
from backend.app.satellite import aoi, gee, indices, service
from backend.app.satellite.models import SatelliteAOI, SatelliteFetchJob, SatelliteObservation


def _session() -> Session:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    return Session(engine)


class AoiValidationTests(unittest.TestCase):
    def test_rejects_missing_and_out_of_range_coordinates(self):
        with self.assertRaises(aoi.AOIValidationError):
            aoi.build_aoi(name="No coordinates")
        with self.assertRaises(aoi.AOIValidationError):
            aoi.build_aoi(name="Bad latitude", latitude=91.0, longitude=80.0)
        with self.assertRaises(aoi.AOIValidationError):
            aoi.build_aoi(name="Bad longitude", latitude=25.0, longitude=181.0)
        with self.assertRaises(aoi.AOIValidationError):
            aoi.build_aoi(name="NaN", latitude=float("nan"), longitude=80.0)

    def test_buffer_limits_are_enforced(self):
        with self.assertRaises(aoi.AOIValidationError):
            aoi.build_aoi(name="Too small", latitude=25.0, longitude=80.0, buffer_m=1)
        with self.assertRaises(aoi.AOIValidationError):
            aoi.build_aoi(name="Too large", latitude=25.0, longitude=80.0, buffer_m=100000)

    def test_buffer_polygon_is_closed_and_has_expected_area(self):
        spec = aoi.build_aoi(
            name="Tehri downstream", latitude=30.3719, longitude=78.4777, buffer_m=300
        )
        ring = spec["geometry"]["coordinates"][0]
        self.assertEqual(ring[0], ring[-1])
        self.assertEqual(spec["kind"], aoi.KIND_POINT_BUFFER)
        self.assertEqual(spec["buffer_m"], 300.0)
        # A 300 m geodesic circle is ~0.2827 km2; allow 2% for the 64-vertex polygon.
        self.assertAlmostEqual(spec["area_km2"], 0.2827, delta=0.006)
        self.assertEqual(spec["latitude"], 30.3719)
        self.assertEqual(spec["longitude"], 78.4777)

    def test_stable_identifier_is_deterministic(self):
        first = aoi.build_aoi(name="A", latitude=30.3719, longitude=78.4777, buffer_m=300)
        second = aoi.build_aoi(name="A renamed", latitude=30.3719, longitude=78.4777, buffer_m=300)
        larger = aoi.build_aoi(name="A", latitude=30.3719, longitude=78.4777, buffer_m=900)
        self.assertEqual(first["aoi_key"], second["aoi_key"])
        self.assertNotEqual(first["aoi_key"], larger["aoi_key"])

    def test_polygon_handling(self):
        polygon = {
            "type": "Polygon",
            "coordinates": [
                [[78.47, 30.37], [78.48, 30.37], [78.48, 30.38], [78.47, 30.38], [78.47, 30.37]]
            ],
        }
        spec = aoi.build_aoi(name="Reach", geometry=polygon)
        self.assertEqual(spec["kind"], aoi.KIND_POLYGON)
        self.assertIsNone(spec["buffer_m"])
        self.assertGreater(spec["area_km2"], 0)

    def test_polygon_rejections(self):
        unclosed = {
            "type": "Polygon",
            "coordinates": [[[78.47, 30.37], [78.48, 30.37], [78.48, 30.38], [78.47, 30.38]]],
        }
        with self.assertRaises(aoi.AOIValidationError):
            aoi.validate_polygon(unclosed)
        with self.assertRaises(aoi.AOIValidationError):
            aoi.validate_polygon({"type": "Point", "coordinates": [78.4, 30.3]})
        with self.assertRaises(aoi.AOIValidationError):
            aoi.validate_polygon("not a geometry")
        multipart = {
            "type": "MultiPolygon",
            "coordinates": [
                [[[78.47, 30.37], [78.48, 30.37], [78.48, 30.38], [78.47, 30.37]]],
                [[[79.47, 31.37], [79.48, 31.37], [79.48, 31.38], [79.47, 31.37]]],
            ],
        }
        with self.assertRaises(aoi.AOIValidationError):
            aoi.validate_polygon(multipart)


class SpectralLogicTests(unittest.TestCase):
    def test_scl_mask_excludes_cloud_shadow_and_no_data(self):
        scl = np.array([[6, 3, 8, 9, 10, 11, 0, 1, 4, 5]], dtype=np.int16)
        mask = indices.scl_valid_mask(scl)
        self.assertEqual(mask.tolist(), [[True, False, False, False, False, False, False, False, True, True]])

    def test_ndwi_formula(self):
        green = np.array([0.2, 0.05, 0.0])
        nir = np.array([0.1, 0.15, 0.0])
        values = indices.ndwi(green, nir)
        self.assertAlmostEqual(float(values[0]), (0.2 - 0.1) / 0.3, places=6)
        self.assertAlmostEqual(float(values[1]), (0.05 - 0.15) / 0.2, places=6)
        self.assertTrue(np.isnan(values[2]))  # zero denominator is not a valid index

    def test_scene_ndwi_applies_reflectance_scale_and_mask(self):
        green_dn = np.array([[1000, 1000]], dtype=np.uint16)
        nir_dn = np.array([[500, 500]], dtype=np.uint16)
        scl = np.array([[4, 9]], dtype=np.int16)  # vegetation valid, cloud high excluded
        values = indices.scene_ndwi(green_dn, nir_dn, scl)
        self.assertAlmostEqual(float(values[0][0]), (1000 - 500) / 1500, places=6)
        self.assertTrue(np.isnan(values[0][1]))
        # Scaling is scale-invariant for a normalised difference.
        unscaled = indices.ndwi(green_dn.astype(float), nir_dn.astype(float))
        self.assertAlmostEqual(float(unscaled[0][0]), float(values[0][0]), places=9)

    def test_monthly_composite_is_per_pixel_median_ignoring_masked_pixels(self):
        first = np.array([[0.2, np.nan], [0.4, 0.1]])
        second = np.array([[0.4, np.nan], [0.2, np.nan]])
        composite = indices.monthly_composite([first, second])
        self.assertAlmostEqual(float(composite[0][0]), 0.3, places=6)
        self.assertAlmostEqual(float(composite[1][0]), 0.3, places=6)
        self.assertAlmostEqual(float(composite[1][1]), 0.1, places=6)
        self.assertTrue(np.isnan(composite[0][1]))

    def test_empty_month_is_not_zero_water(self):
        self.assertIsNone(indices.monthly_composite([]))
        summary = indices.summarize(None, threshold=0.0, scene_count=0)
        self.assertEqual(summary["status"], indices.STATUS_NO_SCENES)
        self.assertIsNone(summary["water_area_km2"])
        self.assertIsNone(summary["ndwi_mean"])

        all_masked = indices.summarize(np.full((4, 4), np.nan), threshold=0.0, scene_count=3)
        self.assertEqual(all_masked["status"], indices.STATUS_NO_VALID_PIXELS)
        self.assertIsNone(all_masked["water_area_km2"])

    def test_water_area_uses_pixel_counting_at_10_metres(self):
        composite = np.array([[0.5, 0.5], [-0.5, np.nan]])
        summary = indices.summarize(composite, threshold=0.0, scene_count=2)
        # 2 water pixels x 100 m2 = 200 m2 = 0.0002 km2
        self.assertAlmostEqual(summary["water_area_km2"], 0.0002, places=9)
        self.assertAlmostEqual(summary["water_fraction"], 2 / 3, places=6)
        self.assertEqual(summary["valid_pixel_count"], 3)
        # 3 valid pixels is below the minimum defensible sample, and that is explicit.
        self.assertEqual(summary["status"], indices.STATUS_BELOW_MIN_PIXELS)

    def test_threshold_changes_water_area(self):
        composite = np.array([[0.3, 0.1]])
        low = indices.summarize(composite, threshold=0.0, scene_count=1)
        high = indices.summarize(composite, threshold=0.2, scene_count=1)
        self.assertGreater(low["water_area_km2"], high["water_area_km2"])

    def test_month_helpers(self):
        self.assertEqual(indices.month_bounds("2025-12"), ("2025-12-01", "2026-01-01"))
        self.assertEqual(indices.month_sequence("2024-11", "2025-02"), ["2024-11", "2024-12", "2025-01", "2025-02"])
        with self.assertRaises(ValueError):
            indices.month_sequence("2025-02", "2024-11")
        self.assertEqual(indices.default_window(24, today="2026-11-15")[1], "2026-10")
        self.assertEqual(len(indices.month_sequence(*indices.default_window(24, today="2026-11-15"))), 24)


class GeeAuthenticationTests(unittest.TestCase):
    def setUp(self):
        gee.reset_for_tests()

    def tearDown(self):
        gee.reset_for_tests()

    def test_missing_project_returns_actionable_error(self):
        with patch.object(gee.settings, "GEE_PROJECT_ID", ""):
            with self.assertRaises(gee.GeeUnavailable) as caught:
                gee.ensure_ready()
        message = str(caught.exception)
        self.assertIn("GEE_PROJECT_ID", message)
        self.assertIn("earthengine authenticate", message)

    def test_missing_credentials_file_returns_actionable_error(self):
        with patch.object(gee.settings, "GEE_PROJECT_ID", "demo-project"), patch.object(
            gee, "_credentials_path", return_value="C:/does/not/exist/key.json"
        ):
            with self.assertRaises(gee.GeeUnavailable) as caught:
                gee.ensure_ready()
        self.assertIn("GOOGLE_APPLICATION_CREDENTIALS", str(caught.exception))

    def test_initialisation_failure_is_reported_not_swallowed(self):
        class ExplodingEe:
            class Filter:  # pragma: no cover - structure only
                def __init__(self, *args, **kwargs):
                    raise AssertionError("must not be reached")

        def fail(*args, **kwargs):
            raise RuntimeError("no valid credentials")

        with patch.object(gee.settings, "GEE_PROJECT_ID", "demo-project"), patch.object(
            gee, "_credentials_path", return_value=""
        ), patch.dict("sys.modules", {"ee": ExplodingEe}):
            with patch.object(ExplodingEe, "Initialize", side_effect=fail, create=True):
                with self.assertRaises(gee.GeeUnavailable) as caught:
                    gee.ensure_ready()
        self.assertIn("RuntimeError", str(caught.exception))

    def test_status_reports_configuration_without_secrets(self):
        with patch.object(gee.settings, "GEE_PROJECT_ID", "demo-project"), patch.object(
            gee.settings, "GOOGLE_APPLICATION_CREDENTIALS", "C:/secrets/key.json"
        ):
            state = gee.status()
        self.assertNotIn("key.json", json.dumps(state))
        self.assertTrue(state["project_configured"])
        self.assertTrue(state["credentials_file_configured"])


def _fake_month(month, *, status=None, ndwi=0.12, area=0.5, scenes=4, valid=500):
    start, end = indices.month_bounds(month)
    return {
        "month": month,
        "period_start": start,
        "period_end": end,
        "collection": "COPERNICUS/S2_SR_HARMONIZED",
        "sensor": "S2A/S2B",
        "resolution_m": 10.0,
        "ndwi_threshold": 0.0,
        "max_cloud_pct": 60,
        "ndwi_mean": ndwi,
        "ndwi_median": ndwi,
        "water_area_km2": area,
        "water_fraction": 0.4,
        "scene_count": scenes,
        "valid_pixel_count": valid,
        "status": status or indices.STATUS_OK,
    }


class PersistenceTests(unittest.TestCase):
    def setUp(self):
        self.db = _session()
        self.aoi, _ = service.get_or_create_aoi(
            self.db, name="Tehri downstream", latitude=30.3719, longitude=78.4777, buffer_m=300
        )

    def tearDown(self):
        self.db.close()

    def test_same_location_reuses_one_aoi(self):
        again, created = service.get_or_create_aoi(
            self.db, name="Tehri downstream", latitude=30.3719, longitude=78.4777, buffer_m=300
        )
        self.assertFalse(created)
        self.assertEqual(again.id, self.aoi.id)
        self.assertEqual(self.db.query(SatelliteAOI).count(), 1)

    def test_buffered_and_polygon_aois_are_distinct(self):
        polygon = {
            "type": "Polygon",
            "coordinates": [[[78.47, 30.37], [78.48, 30.37], [78.48, 30.38], [78.47, 30.37]]],
        }
        other, created = service.get_or_create_aoi(self.db, name="Reach", geometry=polygon)
        self.assertTrue(created)
        self.assertNotEqual(other.aoi_key, self.aoi.aoi_key)

    def test_observations_persist_and_duplicates_are_prevented(self):
        with patch.object(gee, "monthly_ndwi", return_value=_fake_month("2025-01")):
            first, created = service.fetch_month(
                self.db, self.aoi, "2025-01", ndwi_threshold=0.0, max_cloud_pct=60
            )
            second, created_again = service.fetch_month(
                self.db, self.aoi, "2025-01", ndwi_threshold=0.0, max_cloud_pct=60
            )
        self.assertTrue(created)
        self.assertFalse(created_again)
        self.assertEqual(first.id, second.id)
        self.assertEqual(self.db.query(SatelliteObservation).count(), 1)
        self.assertAlmostEqual(second.water_area_km2, 0.5)

    def test_different_threshold_creates_a_separate_record(self):
        with patch.object(gee, "monthly_ndwi", return_value=_fake_month("2025-01")):
            service.fetch_month(self.db, self.aoi, "2025-01", ndwi_threshold=0.0, max_cloud_pct=60)
            service.fetch_month(self.db, self.aoi, "2025-01", ndwi_threshold=0.2, max_cloud_pct=60)
        self.assertEqual(self.db.query(SatelliteObservation).count(), 2)

    def test_fetch_is_incremental(self):
        with patch.object(gee, "monthly_ndwi", side_effect=lambda geometry, month, **kw: _fake_month(month)):
            job = service.start_fetch(
                self.db,
                self.aoi,
                start_month="2025-01",
                end_month="2025-03",
                run_async=False,
            )
            self.assertEqual(job.status, service.STATUS_COMPLETED)
            self.assertEqual(job.months_total, 3)

            second = service.start_fetch(
                self.db,
                self.aoi,
                start_month="2025-01",
                end_month="2025-03",
                run_async=False,
            )
        self.assertEqual(second.months_total, 0)
        self.assertEqual(second.months_skipped, 3)
        self.assertEqual(self.db.query(SatelliteObservation).count(), 3)
        self.assertEqual(self.db.query(SatelliteFetchJob).count(), 2)

    def test_availability_reports_missing_months_honestly(self):
        with patch.object(
            gee,
            "monthly_ndwi",
            side_effect=lambda geometry, month, **kw: _fake_month(
                month, status=indices.STATUS_NO_SCENES, ndwi=None, area=None, scenes=0, valid=0
            )
            if month == "2025-02"
            else _fake_month(month),
        ):
            service.start_fetch(
                self.db, self.aoi, start_month="2025-01", end_month="2025-03", run_async=False
            )

        report = service.availability(
            self.db,
            self.aoi.id,
            start_month="2025-01",
            end_month="2025-04",
            collection="COPERNICUS/S2_SR_HARMONIZED",
            algorithm_version=indices.ALGORITHM_VERSION,
            ndwi_threshold=0.0,
            max_cloud_pct=60,
        )
        self.assertEqual(report["months_expected"], 4)
        self.assertEqual(report["with_data"], ["2025-01", "2025-03"])
        self.assertEqual(report["without_data"][0]["month"], "2025-02")
        self.assertEqual(report["without_data"][0]["reason"], indices.STATUS_NO_SCENES)
        self.assertEqual(report["not_fetched"], ["2025-04"])
        self.assertFalse(report["is_complete"])

    def test_auth_failure_marks_job_failed_without_fake_data(self):
        with patch.object(gee, "monthly_ndwi", side_effect=gee.GeeUnavailable("GEE_PROJECT_ID is not configured.")):
            job = service.start_fetch(
                self.db, self.aoi, start_month="2025-01", end_month="2025-02", run_async=False
            )
        self.assertEqual(job.status, service.STATUS_FAILED)
        self.assertIn("GEE_PROJECT_ID", job.error or "")
        self.assertEqual(self.db.query(SatelliteObservation).count(), 0)

    def test_bad_window_is_rejected(self):
        with self.assertRaises(ValueError):
            service.start_fetch(
                self.db, self.aoi, start_month="2025-03", end_month="2025-01", run_async=False
            )
        with self.assertRaises(ValueError):
            service.start_fetch(self.db, self.aoi, months=12, ndwi_threshold=5.0, run_async=False)


class JobRecoveryTests(unittest.TestCase):
    """Restart recovery and duplicate-submission handling for satellite fetch jobs."""

    def setUp(self):
        gee.reset_for_tests()
        self.db = _session()
        self.aoi, _ = service.get_or_create_aoi(
            self.db, name="Recovery reach", latitude=30.3719, longitude=78.4777, buffer_m=300
        )

    def tearDown(self):
        for job_id in list(service.active_job_ids()):
            service._unregister_active(job_id)
        self.db.close()

    def _job(self, **overrides):
        values = dict(
            aoi_id=self.aoi.id,
            status=service.STATUS_RUNNING,
            start_month="2025-01",
            end_month="2025-03",
            ndwi_threshold=0.0,
            max_cloud_pct=60,
            months_total=3,
            months_completed=1,
            months_skipped=0,
            months_failed=0,
            started_at=datetime.now(timezone.utc),
        )
        values.update(overrides)
        job = SatelliteFetchJob(**values)
        self.db.add(job)
        self.db.commit()
        self.db.refresh(job)
        return job

    def test_stale_running_job_is_marked_interrupted_on_startup(self):
        stale = self._job()

        recovered = service.recover_interrupted_jobs(self.db)

        self.assertEqual(recovered, [stale.id])
        self.db.refresh(stale)
        self.assertEqual(stale.status, service.STATUS_INTERRUPTED)
        self.assertIn("restarted", stale.error or "")
        self.assertIn("1 of 3", stale.error or "")
        self.assertIsNotNone(stale.finished_at)
        # History is preserved: the row, its progress counters and its window survive.
        self.assertEqual(stale.months_completed, 1)
        self.assertEqual(stale.months_total, 3)
        self.assertEqual(stale.start_month, "2025-01")
        self.assertEqual(self.db.query(SatelliteFetchJob).count(), 1)

    def test_recovery_is_idempotent_and_does_not_start_work(self):
        self._job()
        service.recover_interrupted_jobs(self.db)
        self.assertEqual(service.recover_interrupted_jobs(self.db), [])

    def test_recovery_leaves_completed_and_failed_jobs_alone(self):
        done = self._job(status=service.STATUS_COMPLETED, months_completed=3, finished_at=datetime.now(timezone.utc))
        failed = self._job(status=service.STATUS_FAILED, error="existing failure", finished_at=datetime.now(timezone.utc))

        self.assertEqual(service.recover_interrupted_jobs(self.db), [])

        for job in (done, failed):
            self.db.refresh(job)
        self.assertEqual(done.status, service.STATUS_COMPLETED)
        self.assertEqual(failed.status, service.STATUS_FAILED)
        self.assertEqual(failed.error, "existing failure")

    def test_recovery_skips_a_job_whose_worker_is_alive_in_this_process(self):
        live = self._job()
        service._register_active(live.id)
        try:
            self.assertEqual(service.recover_interrupted_jobs(self.db), [])
            self.db.refresh(live)
            self.assertEqual(live.status, service.STATUS_RUNNING)
        finally:
            service._unregister_active(live.id)

    def test_interrupted_job_can_be_retried_incrementally(self):
        # One month already persisted before the interruption.
        with patch.object(gee, "monthly_ndwi", return_value=_fake_month("2025-01")), patch.object(
            gee, "ensure_ready"
        ):
            service.start_fetch(
                self.db, self.aoi, start_month="2025-01", end_month="2025-01", run_async=False
            )
        self.assertEqual(self.db.query(SatelliteObservation).count(), 1)

        stale = self._job(months_completed=1)
        service.recover_interrupted_jobs(self.db)

        fetched = []

        def fake_month(geometry, month, **kwargs):
            fetched.append(month)
            return _fake_month(month)

        with patch.object(gee, "monthly_ndwi", side_effect=fake_month):
            retry = service.start_fetch(
                self.db, self.aoi, start_month="2025-01", end_month="2025-03", run_async=False
            )

        self.assertEqual(fetched, ["2025-02", "2025-03"])
        self.assertEqual(retry.months_skipped, 1)
        self.assertEqual(retry.months_total, 2)
        self.assertEqual(retry.status, service.STATUS_COMPLETED)
        self.assertEqual(self.db.query(SatelliteObservation).count(), 3)
        # The interrupted job keeps its own history next to the original and the retry.
        self.db.refresh(stale)
        self.assertEqual(stale.status, service.STATUS_INTERRUPTED)
        self.assertEqual(self.db.query(SatelliteFetchJob).count(), 3)

    def test_duplicate_concurrent_submission_reuses_the_active_job(self):
        active = self._job(status=service.STATUS_QUEUED, months_completed=0)

        job = service.start_fetch(
            self.db, self.aoi, start_month="2025-01", end_month="2025-03"
        )

        self.assertEqual(job.id, active.id)
        self.assertTrue(getattr(job, "reused_active_job", False))
        self.assertEqual(self.db.query(SatelliteFetchJob).count(), 1)
        # No second worker was registered for the duplicate request.
        self.assertEqual(service.active_job_ids(), set())

    def test_non_overlapping_window_is_not_treated_as_a_duplicate(self):
        self._job(status=service.STATUS_QUEUED, start_month="2024-01", end_month="2024-03")

        with patch.object(gee, "monthly_ndwi", side_effect=lambda g, m, **k: _fake_month(m)):
            job = service.start_fetch(
                self.db, self.aoi, start_month="2025-01", end_month="2025-02", run_async=False
            )

        self.assertFalse(getattr(job, "reused_active_job", False))
        self.assertEqual(self.db.query(SatelliteFetchJob).count(), 2)
        self.assertEqual(job.status, service.STATUS_COMPLETED)


# --------------------------------------------------------------------- fake `ee`
#
# A stand-in for the Earth Engine Python API that implements exactly the surface used by
# `backend/app/satellite/gee.py` and nothing more. Tests drive the *real* production query:
# the module is injected into `sys.modules["ee"]`, so `import ee` inside `_initialize()`
# resolves to this object and every production call goes through it.


class FakeReduction:
    """A computed Earth Engine value; ``getInfo()`` returns the scripted result."""

    def __init__(self, value):
        self._value = value

    def getInfo(self):
        return self._value


class FakeImage:
    """Records each operation production code applies to an image."""

    def __init__(self, engine, op, detail=None):
        self._engine = engine
        self.op = op
        self.detail = detail or {}

    def set(self, key, value):
        self._engine.record("set", (key, value))
        return self

    def select(self, band):
        self._engine.record("select", band)
        return FakeImage(self._engine, "select", {"band": band})

    def neq(self, value):
        self._engine.record("neq", value)
        return FakeImage(self._engine, "neq", {"value": value})

    def And(self, other):
        self._engine.record("And", getattr(other, "op", other))
        return FakeImage(self._engine, "and")

    def normalizedDifference(self, bands):
        self._engine.record("normalizedDifference", list(bands))
        return FakeImage(self._engine, "ndwi", {"bands": list(bands)})

    def rename(self, name):
        self._engine.record("rename", name)
        return FakeImage(self._engine, "ndwi", self.detail)

    def updateMask(self, mask):
        self._engine.record("updateMask", getattr(mask, "op", mask))
        return FakeImage(self._engine, "ndwi_masked")

    def copyProperties(self, image, properties):
        self._engine.record("copyProperties", list(properties))
        return self

    def mask(self):
        self._engine.record("mask")
        return FakeImage(self._engine, "mask")

    def gt(self, value):
        self._engine.record("gt", value)
        return FakeImage(self._engine, "valid" if self.op == "mask" else "water", {"value": value})

    def gte(self, value):
        self._engine.record("gte", value)
        return FakeImage(self._engine, "water", {"value": value})

    def multiply(self, other):
        self._engine.record("multiply", getattr(other, "op", other))
        return FakeImage(self._engine, "water_area" if self.op == "water" else "valid_area")

    def reduceRegion(self, **kwargs):
        return FakeReduction(self._engine.reduce(self, kwargs))


class FakeImageFactory:
    """Mimics ``ee.Image``: callable for ``ee.Image(1)`` and a namespace for ``pixelArea()``."""

    def __init__(self, engine):
        self._engine = engine

    def __call__(self, value):
        self._engine.record("Image", value)
        return FakeImage(self._engine, "base", {"value": value})

    def pixelArea(self):
        self._engine.record("pixelArea")
        return FakeImage(self._engine, "pixel_area")

    def set(self, key, value):
        self._engine.record("set", (key, value))
        return self


class FakeGeometry:
    def __init__(self, geo_json):
        self.geo_json = geo_json


class FakeCollection:
    def __init__(self, engine, collection_id):
        self._engine = engine
        self.collection_id = collection_id

    def filterBounds(self, geometry):
        self._engine.record("filterBounds", geometry)
        return self

    def filterDate(self, start, end):
        self._engine.record("filterDate", (start, end))
        return self

    def filter(self, expression):
        self._engine.record("filter", expression)
        return self

    def size(self):
        self._engine.record("size")
        return FakeReduction(self._engine.scene_count)

    def map(self, callback):
        self._engine.record("map")
        # Runs the production masking closure on a fake scene so its SCL/NDWI
        # operations are recorded exactly as written.
        self._engine.capture(lambda: callback(FakeImage(self._engine, "scene")))
        return self

    def median(self):
        self._engine.record("median")
        self._engine.assert_masked()
        return FakeImage(self._engine, "composite")

    def aggregate_array(self, property_name):
        self._engine.record("aggregate_array", property_name)
        return FakeReduction(list(self._engine.sensors))



class FakeEarthEngine:
    """Minimal ``ee`` module implementation for the production Sentinel-2 query."""

    def __init__(
        self,
        *,
        scene_count=4,
        ndwi_mean=0.12,
        ndwi_median=0.10,
        valid_pixels=500,
        water_area_m2=20000.0,
        valid_area_m2=50000.0,
        sensors=("S2A", "S2B"),
        fail_reduce_at=None,
    ):
        self.scene_count = scene_count
        self.ndwi_mean = ndwi_mean
        self.ndwi_median = ndwi_median
        self.valid_pixels = valid_pixels
        self.water_area_m2 = water_area_m2
        self.valid_area_m2 = valid_area_m2
        self.sensors = tuple(sensors)
        self.fail_reduce_at = fail_reduce_at
        self.calls = []
        self.mask_calls = []
        self.reduce_calls = []
        self._capturing = False
        self.Filter = SimpleNamespace(lt=self._filter_lt)
        self.Reducer = SimpleNamespace(
            mean=lambda: SimpleNamespace(name="mean"),
            median=lambda: SimpleNamespace(name="median"),
            sum=lambda: SimpleNamespace(name="sum"),
        )
        self.Image = FakeImageFactory(self)

    # -- module-level entry points -------------------------------------------------
    def Initialize(self, **kwargs):
        self.calls.append(("Initialize", kwargs))

    def Geometry(self, geo_json, crs=None, geodesic=None):
        self.calls.append(("Geometry", geo_json, crs, geodesic))
        return FakeGeometry(geo_json)

    def ImageCollection(self, collection_id):
        self.calls.append(("ImageCollection", collection_id))
        return FakeCollection(self, collection_id)

    def _filter_lt(self, name, value):
        expression = ("Filter.lt", name, value)
        self.calls.append(expression)
        return expression

    # -- recording helpers ---------------------------------------------------------
    def record(self, name, detail=None):
        self.calls.append((name, detail))
        if self._capturing:
            self.mask_calls.append((name, detail))

    def capture(self, callback):
        self._capturing = True
        try:
            return callback()
        finally:
            self._capturing = False

    def assert_masked(self):
        if not any(call[0] == "map" for call in self.calls):
            raise AssertionError("median() ran before map(): the SCL mask closure was skipped")

    def reduce(self, image, kwargs):
        self.reduce_calls.append((image.op, kwargs))
        if self.fail_reduce_at is not None and len(self.reduce_calls) == self.fail_reduce_at:
            raise RuntimeError("EEException: user memory limit exceeded")
        reducer = kwargs["reducer"].name
        if image.op == "composite":
            if reducer == "mean":
                return {"NDWI": self.ndwi_mean}
            if reducer == "median":
                return {"NDWI": self.ndwi_median}
        if image.op == "valid" and reducer == "sum":
            return {"constant": self.valid_pixels}
        if image.op == "water_area":
            return {"constant": self.water_area_m2}
        if image.op == "valid_area":
            return {"constant": self.valid_area_m2}
        raise AssertionError(f"unexpected reduction: {image.op}/{reducer}")

    # -- convenience ---------------------------------------------------------------
    def called(self, name):
        return [call for call in self.calls if call[0] == name]


def run_monthly_query(engine, geometry, month="2025-01", threshold=0.0, cloud=60):
    """Invoke the production query with the fake module installed as ``ee``."""
    gee.reset_for_tests()
    try:
        with patch.object(gee.settings, "GEE_PROJECT_ID", "fake-project"), patch.object(
            gee, "_credentials_path", return_value=""
        ), patch.dict(sys.modules, {"ee": engine}):
            return gee.monthly_ndwi(geometry, month, ndwi_threshold=threshold, max_cloud_pct=cloud)
    finally:
        gee.reset_for_tests()


class EarthEngineQueryTests(unittest.TestCase):
    """Drives the real `gee.monthly_ndwi` implementation against the fake `ee` module.

    This exercises production query construction (collection, bounds, dates, cloud filter,
    SCL mask closure, median composite, reductions) and result parsing. It does not contact
    Google, does not authenticate, and does not prove that live Earth Engine works.
    """

    geometry = aoi.build_aoi(name="Fixture reach", latitude=30.3719, longitude=78.4777, buffer_m=300)[
        "geometry"
    ]

    def test_query_sends_expected_collection_filters_and_reductions(self):
        engine = FakeEarthEngine()
        result = run_monthly_query(engine, self.geometry, threshold=0.1, cloud=40)

        # Initialisation used the configured project, without interactive auth.
        self.assertEqual(engine.called("Initialize")[0][1], {"project": "fake-project"})

        # Collection, AOI bounds, month window, and per-scene cloud filter.
        self.assertEqual(engine.called("ImageCollection")[0][1], "COPERNICUS/S2_SR_HARMONIZED")
        self.assertEqual(engine.called("filterBounds")[0][1].geo_json, self.geometry)
        self.assertEqual(engine.called("filterDate")[0][1], ("2025-01-01", "2025-02-01"))
        self.assertIn(
            ("Filter.lt", "CLOUDY_PIXEL_PERCENTAGE", 40), engine.called("Filter.lt")
        )
        self.assertEqual(engine.called("Geometry")[0][1], self.geometry)
        self.assertFalse(engine.called("Geometry")[0][3])  # geodesic=False

        # The production masking closure ran inside map().
        self.assertEqual(engine.called("map")[0][0], "map")
        mask_ops = [name for name, _ in engine.mask_calls]
        self.assertIn("select", mask_ops)
        self.assertEqual([detail for name, detail in engine.mask_calls if name == "select"], ["SCL"])
        self.assertEqual(
            {detail for name, detail in engine.mask_calls if name == "neq"}, {0, 1, 3, 8, 9, 10, 11}
        )
        self.assertEqual(
            [detail for name, detail in engine.mask_calls if name == "normalizedDifference"],
            [["B3", "B8"]],
        )
        self.assertIn("updateMask", mask_ops)
        self.assertIn("copyProperties", mask_ops)

        # Monthly aggregation happened on the masked collection.
        self.assertEqual(engine.called("median")[0][0], "median")
        self.assertEqual([op for op, _ in engine.reduce_calls], [
            "composite", "composite", "valid", "water_area", "valid_area",
        ])

        # Every reduction used the fixed 10 m grid on ONE projected CRS derived from the AOI
        # (UTM zone 44N for 78.48 E / 30.37 N), never WGS84 and never bestEffort.
        default_crs = "EPSG:32644"
        for _, kwargs in engine.reduce_calls:
            self.assertEqual(kwargs["scale"], 10)
            self.assertEqual(kwargs["crs"], default_crs)
            self.assertEqual(kwargs["maxPixels"], 1_000_000_000)
            self.assertFalse(kwargs["bestEffort"])
            self.assertEqual(kwargs["tileScale"], 4)
            self.assertEqual(kwargs["geometry"].geo_json, self.geometry)

        # All five reductions share one grid: mean/median NDWI and both area sums are taken
        # on the same projection, so no reduction silently resamples the composite.
        self.assertEqual({kw["crs"] for _, kw in engine.reduce_calls}, {default_crs})
        self.assertEqual(result["projection"], default_crs)

        # Pixel area is measured in projected metres, so the square-metre sum is physical:
        # 20 000 m2 of water over a 300 m radius AOI is 0.02 km2.
        self.assertAlmostEqual(result["water_area_km2"], 0.02)

        # Result parsing: reduced values into the persisted record shape.
        self.assertEqual(result["status"], indices.STATUS_OK)
        self.assertEqual(result["month"], "2025-01")
        self.assertEqual(result["period_start"], "2025-01-01")
        self.assertEqual(result["period_end"], "2025-02-01")
        self.assertAlmostEqual(result["ndwi_mean"], 0.12)
        self.assertAlmostEqual(result["ndwi_median"], 0.10)
        self.assertAlmostEqual(result["water_area_km2"], 0.02)      # 20 000 m2
        self.assertAlmostEqual(result["water_fraction"], 0.4)       # 20 000 / 50 000
        self.assertEqual(result["valid_pixel_count"], 500)
        self.assertEqual(result["scene_count"], 4)
        self.assertEqual(result["ndwi_threshold"], 0.1)
        self.assertEqual(result["max_cloud_pct"], 40)
        self.assertEqual(result["sensor"], "S2A/S2B")
        self.assertEqual(result["collection"], "COPERNICUS/S2_SR_HARMONIZED")
        self.assertEqual(result["resolution_m"], 10.0)

    def test_threshold_is_passed_to_the_water_area_reduction(self):
        engine = FakeEarthEngine()
        run_monthly_query(engine, self.geometry, threshold=0.35)
        self.assertIn("water_area", [op for op, _ in engine.reduce_calls])
        self.assertEqual([call[1] for call in engine.calls if call[0] == "gte"], [0.35])

    def test_no_scenes_short_circuits_without_fabricated_measurements(self):
        engine = FakeEarthEngine(scene_count=0)
        result = run_monthly_query(engine, self.geometry)
        self.assertEqual(result["status"], indices.STATUS_NO_SCENES)
        self.assertIsNone(result["ndwi_mean"])
        self.assertIsNone(result["water_area_km2"])
        self.assertEqual(result["scene_count"], 0)
        self.assertIsNone(result["sensor"])
        self.assertEqual(engine.reduce_calls, [])
        self.assertEqual(engine.called("map"), [])

    def test_fully_masked_month_reports_no_valid_pixels(self):
        engine = FakeEarthEngine(ndwi_mean=None, ndwi_median=None, valid_pixels=0)
        result = run_monthly_query(engine, self.geometry)
        self.assertEqual(result["status"], indices.STATUS_NO_VALID_PIXELS)
        self.assertIsNone(result["ndwi_mean"])
        self.assertIsNone(result["water_area_km2"])
        self.assertEqual(result["valid_pixel_count"], 0)

    def test_sparse_month_is_flagged_but_keeps_the_measurement(self):
        engine = FakeEarthEngine(valid_pixels=10)
        result = run_monthly_query(engine, self.geometry)
        self.assertEqual(result["status"], indices.STATUS_BELOW_MIN_PIXELS)
        self.assertAlmostEqual(result["water_area_km2"], 0.02)

    def test_missing_sensor_property_is_tolerated(self):
        engine = FakeEarthEngine(sensors=())
        result = run_monthly_query(engine, self.geometry)
        self.assertEqual(result["sensor"], "S2A/S2B/S2C")

    def test_reduction_failure_is_reported_as_a_query_error(self):
        engine = FakeEarthEngine(fail_reduce_at=1)
        with self.assertRaises(gee.GeeQueryError) as caught:
            run_monthly_query(engine, self.geometry)
        self.assertIn("reducing Sentinel-2 imagery", str(caught.exception))

    def test_query_requires_a_configured_project(self):
        gee.reset_for_tests()
        try:
            with patch.object(gee.settings, "GEE_PROJECT_ID", ""), patch.object(
                gee, "_credentials_path", return_value=""
            ), patch.dict(sys.modules, {"ee": FakeEarthEngine()}):
                with self.assertRaises(gee.GeeUnavailable):
                    gee.monthly_ndwi(self.geometry, "2025-01", ndwi_threshold=0.0, max_cloud_pct=60)
        finally:
            gee.reset_for_tests()


class ProjectionStrategyTests(unittest.TestCase):
    """Verifies the locally-derived projected CRS used for every Earth Engine reduction.

    The strategy is: one UTM zone (or polar stereographic near the poles) chosen from the AOI
    centroid, so `scale` is metres and pixelArea sums are square metres at any latitude.
    """

    def test_zone_is_derived_from_the_aoi_not_hardcoded(self):
        # Same latitude, three very different longitudes: three different zones.
        self.assertEqual(gee._utm_crs(78.4777, 30.3719), "EPSG:32644")   # India, 44N
        self.assertEqual(gee._utm_crs(-74.006, 40.7128), "EPSG:32618")   # New York, 18N
        self.assertEqual(gee._utm_crs(151.2093, -33.8688), "EPSG:32756")  # Sydney, 56S

    def test_utm_zone_boundaries_are_inclusive_of_the_west_edge(self):
        # Zone N spans [6N-180, 6N-174); lon exactly on a boundary belongs to the new zone.
        self.assertEqual(gee._utm_crs(-180.0, 10.0), "EPSG:32601")
        self.assertEqual(gee._utm_crs(-174.0, 10.0), "EPSG:32602")
        self.assertEqual(gee._utm_crs(77.9, 10.0), "EPSG:32643")
        self.assertEqual(gee._utm_crs(78.0, 10.0), "EPSG:32644")
        # Longitudes outside [-180, 180] are clamped into a valid zone, never a crash.
        self.assertEqual(gee._utm_crs(185.0, 10.0), "EPSG:32601")

    def test_southern_hemisphere_uses_the_south_zone_series(self):
        self.assertEqual(gee._utm_crs(78.4777, -30.3719), "EPSG:32744")
        self.assertEqual(gee._utm_crs(78.4777, -0.0001), "EPSG:32744")
        self.assertEqual(gee._utm_crs(78.4777, 0.0001), "EPSG:32644")

    def test_polar_aois_fall_back_to_polar_stereographic(self):
        # UTM is not defined beyond +84 N / -80 S; those AOIs get a polar stereographic CRS
        # rather than an out-of-range zone.
        self.assertEqual(gee._utm_crs(20.0, 85.0), "EPSG:3995")
        self.assertEqual(gee._utm_crs(20.0, -81.0), "EPSG:3031")

    def test_no_reduction_uses_a_geographic_crs(self):
        # A geographic CRS makes `scale=10` mean 10 degrees, so the pixel's ground size grows
        # as 1/cos(lat). Assert the derived CRS is always projected.
        for lon in (-170.0, -60.0, 0.0, 78.5, 140.0):
            for lat in (-70.0, -10.0, 0.0, 30.0, 70.0):
                crs = gee._utm_crs(lon, lat)
                self.assertRegex(crs, r"^EPSG:(326|327)\d{2}$|^EPSG:(3995|3031)$")
                self.assertNotIn(crs, {"EPSG:4326", "EPSG:4979"})

    def test_representative_point_reads_geojson_polygons(self):
        geometry = aoi.build_aoi(
            name="Fixture", latitude=30.3719, longitude=78.4777, buffer_m=300
        )["geometry"]
        lon, lat = gee._representative_point(geometry)
        self.assertAlmostEqual(lon, 78.4777, places=3)
        self.assertAlmostEqual(lat, 30.3719, places=3)
        # The derived CRS therefore matches the AOI centre's zone.
        self.assertEqual(gee._utm_crs(lon, lat), "EPSG:32644")


class ApiTests(unittest.TestCase):
    """Exercises route handlers directly with a real session and a fake current user."""

    def setUp(self):
        from backend.app.api import satellite as satellite_api

        self.api = satellite_api
        self.db = _session()
        self.user = type("U", (), {"id": 1, "username": "tester", "role": "researcher", "is_active": True})()

    def tearDown(self):
        self.db.close()

    def resolve(self, **overrides):
        payload = dict(name="Tehri downstream", latitude=30.3719, longitude=78.4777, buffer_m=300)
        payload.update(overrides)
        body = self.api.AoiResolveRequest(**payload)
        return self.api.resolve_aoi(body, self.db)

    def test_resolve_and_read_back(self):
        first = self.resolve()
        self.assertTrue(first["created"])
        aoi_id = first["aoi"]["id"]
        again = self.resolve(name="Tehri downstream renamed")
        self.assertFalse(again["created"])
        self.assertEqual(again["aoi"]["id"], aoi_id)
        self.assertEqual(again["aoi"]["name"], "Tehri downstream renamed")
        self.assertEqual(self.api.get_aoi(aoi_id, self.db)["aoi"]["kind"], "point_buffer")

    def test_status_endpoint_is_safe(self):
        state = self.api.satellite_status()
        self.assertIn("package_installed", state["earth_engine"])
        self.assertEqual(state["defaults"]["collection"], "COPERNICUS/S2_SR_HARMONIZED")

    def test_observations_endpoint_surfaces_missing_data(self):
        aoi_id = self.resolve()["aoi"]["id"]
        empty = self.api.get_observations(
            aoi_id, "2025-01", "2025-02", None, None, self.db
        )
        self.assertEqual(empty["items"], [])
        self.assertEqual(empty["availability"]["months_not_fetched"], 2)
        self.assertIn("not a measurement", empty["caveat"])

    def test_fetch_returns_503_when_gee_is_unconfigured(self):
        from fastapi import HTTPException

        aoi_id = self.resolve()["aoi"]["id"]
        with patch.object(gee.settings, "GEE_PROJECT_ID", ""):
            with self.assertRaises(HTTPException) as caught:
                self.api.start_fetch(aoi_id, self.api.SatelliteFetchRequest(months=2), self.db)
        self.assertEqual(caught.exception.status_code, 503)
        self.assertIn("GEE_PROJECT_ID", caught.exception.detail)

    def test_fetch_queues_job_when_gee_is_ready(self):
        aoi_id = self.resolve()["aoi"]["id"]
        with patch.object(gee, "ensure_ready", return_value={}), patch.object(
            service, "start_fetch"
        ) as queued:
            queued.return_value = SatelliteFetchJob(
                id=7,
                aoi_id=aoi_id,
                status="queued",
                start_month="2025-01",
                end_month="2025-02",
                ndwi_threshold=0.0,
                max_cloud_pct=60,
                months_total=2,
                months_completed=0,
                months_skipped=0,
                months_failed=0,
            )
            self.db.add(queued.return_value)
            self.db.commit()
            response = self.api.start_fetch(
                aoi_id, self.api.SatelliteFetchRequest(start_month="2025-01", end_month="2025-02"), self.db
            )
        self.assertEqual(response["job"]["status"], "queued")
        self.assertEqual(response["job"]["months_total"], 2)

    def test_invalid_aoi_request_is_rejected_by_schema(self):
        from pydantic import ValidationError

        with self.assertRaises(ValidationError):
            self.api.AoiResolveRequest(name="No location")
        with self.assertRaises(ValidationError):
            self.api.SatelliteFetchRequest(start_month="2025-01")
        with self.assertRaises(ValidationError):
            self.api.SatelliteFetchRequest(start_month="2025-03", end_month="2025-01")


if __name__ == "__main__":
    unittest.main()
