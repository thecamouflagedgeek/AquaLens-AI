"""Transparent exploratory fingerprint comparisons, never a chemical safety test."""
import numpy as np
from .ml.feature_schema import FEATURE_NAMES

MIN_REFERENCE = 5
THRESHOLD = 2.5
LIMITATIONS = (
    'Exploratory visual monitoring only; no Indian-domain performance validation is claimed. '
    'Five reference samples enable calculation, not scientific validation. '
    'The mean absolute IQR-scaled deviation and 2.5 screening threshold are heuristic. '
    'Visual Stability Score = 100 × exp(-0.35 × mean absolute normalized deviation); '
    'it does not establish pollution, chemical safety or potability. '
    'Distinct image checksums do not establish sampling independence. Comparisons are retrospective against the selected frozen reference version. '
    'Season labels and contextual measurements are entered by the operator; no causal attribution is made.'
)


def build_reference(observations):
    if len(observations) < MIN_REFERENCE:
        raise ValueError('At least five distinct eligible reference images are required.')
    matrix = np.array([[o['features'][f] for f in FEATURE_NAMES] for o in observations], dtype=float)
    if not np.isfinite(matrix).all():
        raise ValueError('Reference features must be finite.')
    return {f: {'median': float(np.median(matrix[:, i])),
                'q25': float(np.percentile(matrix[:, i], 25)),
                'q75': float(np.percentile(matrix[:, i], 75)),
                'iqr': float(np.percentile(matrix[:, i], 75) - np.percentile(matrix[:, i], 25))}
            for i, f in enumerate(FEATURE_NAMES)}


def compare(observation, reference, previous=None):
    same_context = bool(reference and observation['season'] == reference['season']
                        and observation['capture_protocol'] == reference['capture_protocol'])
    if same_context and reference.get('capture_settings'):
        same_context = all(observation.get(key) == value for key, value in reference['capture_settings'].items())
    features = []
    for name in FEATURE_NAMES:
        current = observation.get('features', {}).get(name)
        stats = reference['stats'].get(name) if same_context else None
        delta = current - stats['median'] if stats and current is not None else None
        normalized = (delta / stats['iqr'] if stats['iqr'] > 1e-9 else (0.0 if abs(delta) < 1e-9 else None)) if delta is not None else None
        prior = previous.get('features', {}).get(name) if previous else None
        features.append({'name': name, 'current': current, 'previous': prior,
                         'previous_delta': current - prior if current is not None and prior is not None else None,
                         'baseline': stats, 'deviation': delta, 'normalized_deviation': normalized})
    normalized = [abs(f['normalized_deviation']) for f in features if f['normalized_deviation'] is not None]
    # Partial comparisons are shown, but no complete-vector score is claimed when a scale is undefined.
    complete = same_context and len(normalized) == len(FEATURE_NAMES)
    score = float(np.mean(normalized)) if complete else None
    is_reference = bool(reference and observation['id'] in reference['observation_ids'])
    status = ('reference_sample' if is_reference else
              'insufficient_baseline' if not reference else
              'context_mismatch' if not same_context else
              'undefined_feature_scale' if not complete else
              'potential_anomaly' if score > THRESHOLD else 'within_screening_threshold')
    return {'observation_id': observation['id'], 'features': features, 'anomaly_score': score,
            'visual_stability_score': round(100 * float(np.exp(-0.35 * score)), 1) if score is not None and not is_reference else None,
            'status': status, 'threshold': THRESHOLD, 'is_reference_sample': is_reference,
            'comparable_features': len(normalized), 'limitations': LIMITATIONS}
