"""Isolated India workflow tests. Synthetic fixtures never enter the application DB."""
import asyncio
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np
from fastapi import FastAPI, HTTPException, Response
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from starlette.datastructures import UploadFile

from backend.app.api import india
from backend.app.db.session import Base
from backend.app.db.models import User
from backend.app.india_models import IndiaObservation, IndiaRecord
from backend.app.india_analysis import build_reference, compare
from backend.app.ml.feature_schema import FEATURE_NAMES
from backend.app.water_validation import result


class IndiaWorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://')
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.station = india.register_station(india.StationInput(name='Test-only sampling point', river='Ganga', state='Test state', latitude=25.0, longitude=82.0, coordinate_source='Synthetic unit-test coordinate'), self.db)

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def sample(self, value, **changes):
        payload = dict(timestamp=(datetime(2025, 1, 1, tzinfo=timezone.utc) + timedelta(days=value)).isoformat(), season='Winter', capture_protocol='test-v1', camera='test camera', camera_settings='test settings', illumination='test light', preparation='test chamber', eligible=True, features={f: float(value) for f in FEATURE_NAMES}, classification=None)
        payload.update(changes)
        row = IndiaObservation(station_id=self.station['id'], checksum=f'test-{value}', filename='not-a-real-image', payload=json.dumps(payload))
        self.db.add(row)
        self.db.commit()
        return india.unpack(row)

    def baseline(self):
        samples = [self.sample(i) for i in range(1, 6)]
        return india.create_reference(self.station['id'], india.ReferenceInput(observation_ids=[o['id'] for o in samples], season='Winter', capture_protocol='test-v1', notes='Synthetic reference for unit tests only'), self.db)

    def test_workspace_access_is_enforced_on_server(self):
        self.assertEqual(india.india_user(User(username='admin_1')).workspace, 'india')
        with self.assertRaises(HTTPException) as raised:
            india.india_user(User(username='admin'))
        self.assertEqual(raised.exception.status_code, 403)
        with self.assertRaises(HTTPException):
            india.require_station(self.db, 987654)

    def test_fingerprint_is_season_and_capture_specific(self):
        reference = self.baseline()
        sample = self.sample(20)
        result = compare(sample, reference)
        self.assertEqual(result['status'], 'potential_anomaly')
        self.assertAlmostEqual(result['anomaly_score'], 8.5)
        self.assertEqual(len(result['features']), 20)
        self.assertIsNone(compare({**sample, 'season': 'Monsoon'}, reference)['anomaly_score'])
        self.assertIsNone(compare({**sample, 'camera_settings': 'changed'}, reference)['anomaly_score'])
        self.assertEqual(compare(india.observations(self.db, self.station['id'])[-1], reference)['status'], 'reference_sample')

    def test_blocked_field_photo_is_kept_for_review_without_affecting_analysis(self):
        reference = self.baseline()
        rejected = self.sample(6, ground={'location_status': 'admin_verified'},
                               water_validation=result('NO_WATER_DETECTED', 'Empty container', 2.5))
        valid = self.sample(7, ground={'location_status': 'admin_verified'},
                            water_validation=result('VALID_WATER_SOURCE', 'Visible water', 90))
        analysis = india.station_analysis(self.station['id'], observation_id=valid['id'], db=self.db)
        blocked = next(o for o in analysis['observations'] if o['id'] == rejected['id'])
        self.assertEqual(blocked['water_validation']['status'], 'NO_WATER_DETECTED')
        self.assertEqual(blocked['features'], {})
        self.assertIsNone(compare(blocked, reference)['visual_stability_score'])
        self.assertNotIn(blocked['id'], [point['id'] for point in analysis['timeline']])
        self.assertEqual(analysis['previous']['id'], reference['observation_ids'][-1])

    def test_missing_and_zero_spread_data_are_not_zero_scores(self):
        samples = [self.sample(i, features={f: 1.0 for f in FEATURE_NAMES}) for i in range(1, 6)]
        reference = dict(stats=build_reference(samples), observation_ids=[o['id'] for o in samples], season='Winter', capture_protocol='test-v1')
        changed = self.sample(12, features={f: 2.0 for f in FEATURE_NAMES})
        self.assertIsNone(compare(changed, reference)['visual_stability_score'])
        self.assertEqual(compare(changed, reference)['status'], 'undefined_feature_scale')
        self.assertEqual(compare(changed, None)['status'], 'insufficient_baseline')

    def test_persistence_pairing_followup_and_report(self):
        self.baseline()
        for value in (30, 31, 32):
            sample = self.sample(value)
        analysis = india.station_analysis(self.station['id'], db=self.db)
        self.assertTrue(analysis['comparison']['persistent_screening_flag'])
        self.assertTrue(analysis['reference_observation'])
        history = {row['id']: row for row in analysis['timeline']}
        self.assertEqual(history[analysis['reference_observation']['id']]['feature_deviations'], {})
        for feature in analysis['comparison']['features']:
            scale = feature['baseline']['iqr']
            self.assertAlmostEqual(history[sample['id']]['feature_deviations'][feature['name']],
                                   (sample['features'][feature['name']] - feature['baseline']['median']) / scale)

        record = india.EvidenceInput(observation_id=sample['id'], parameter='pH', value=7.2, unit='dimensionless', timestamp=datetime.now(timezone.utc), provenance='Synthetic test laboratory')
        india.add_evidence(self.station['id'], 'laboratory', record, self.db)
        action = india.add_action(self.station['id'], india.ActionInput(observation_id=sample['id'], concern='Test visual departure', evidence='Unit-test feature comparison', suggested_action='Repeat the unit-test observation'), self.db)
        updated = india.update_action(action['id'], india.ActionUpdate(status='Reviewed', remarks='Test follow-up saved'), self.db)
        self.assertEqual(updated['status'], 'Reviewed')
        self.assertEqual(len(updated['history']), 1)
        report = india.export_report(self.station['id'], db=self.db)
        self.assertIn(b'Test follow-up saved', report.body)
        self.assertIn(b'chemical safety', report.body)
        self.assertIn(b'Synthetic test laboratory', report.body)
        with self.assertRaises(HTTPException):
            india.add_evidence(self.station['id'], 'laboratory', record.model_copy(update={'observation_id': 9999}), self.db)

    def test_baseline_rejects_duplicates_ineligible_and_mixed_capture(self):
        samples = [self.sample(i) for i in range(1, 6)]
        body = india.ReferenceInput(observation_ids=[samples[0]['id']] * 5, season='Winter', capture_protocol='test-v1', notes='Test selection')
        with self.assertRaises(HTTPException):
            india.create_reference(self.station['id'], body, self.db)
        row = self.db.get(IndiaObservation, samples[-1]['id'])
        payload = json.loads(row.payload)
        payload['camera'] = 'another camera'
        row.payload = json.dumps(payload)
        self.db.commit()
        with self.assertRaises(HTTPException):
            india.create_reference(self.station['id'], body.model_copy(update={'observation_ids': [o['id'] for o in samples]}), self.db)

    def test_upload_retains_original_when_rf_is_unavailable_and_rejects_duplicates(self):
        _, encoded = cv2.imencode('.png', np.full((40, 40, 3), 127, dtype=np.uint8))
        contents = encoded.tobytes()
        meta = india.SampleMetadata(timestamp=datetime(2025, 1, 1, tzinfo=timezone.utc), season='Winter', camera='Test camera', camera_settings='Fixed test settings', illumination='Test light', preparation='Test chamber', capture_protocol='Test protocol')
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory, patch.object(india, 'FILES', Path(directory)), patch.object(india, 'get_inference_engine', side_effect=RuntimeError('Test RF unavailable')):
            result = asyncio.run(india.upload_observation(self.station['id'], meta.model_dump_json(), UploadFile(filename='test.png', file=BytesIO(contents)), self.db))
            self.assertEqual(result['processing_status'], 'features_extracted')
            self.assertEqual(len(result['features']), 20)
            response = india.sample_image(result['id'], self.db)
            self.assertEqual(Path(response.path).read_bytes(), contents)
            self.assertEqual(response.media_type, 'image/png')
            with self.assertRaises(HTTPException) as raised:
                asyncio.run(india.upload_observation(self.station['id'], meta.model_dump_json(), UploadFile(filename='duplicate.png', file=BytesIO(contents)), self.db))
            self.assertEqual(raised.exception.status_code, 409)


if __name__ == '__main__':
    unittest.main()
