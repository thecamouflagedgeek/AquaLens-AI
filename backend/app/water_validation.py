"""Screen officer photos before they enter the visual analysis pipeline."""
from functools import lru_cache
import logging
import os
from pathlib import Path

import cv2
import numpy as np

VALID = 'VALID_WATER_SOURCE'
REVIEW = 'REVIEW_REQUIRED'
MODEL = 'openai/clip-vit-base-patch32'
REVISION = '3d74acf'
METHOD = 'clip-water-screening-v2'

WATER = (
    'a river, lake or pond with a visible water surface',
    'a glass or transparent bowl containing clear water',
    'a close-up looking down into a container of transparent water with small bubbles on the liquid surface',
    'a side view of a partially filled glass with a visible water line and reflections',
    'a container holding a sample of muddy water',
    'a body of water with green algae on the water surface',
)
NON_WATER = (
    'an empty transparent glass or empty sample container',
    'an overhead view of the dry bottom of an empty glass bowl',
    'a selfie or portrait with no water visible',
    'a dry road or pavement with no water visible',
    'a building or indoor room with no water visible',
    'an ordinary object or dry landscape with no water visible',
)
OBSCURED = ('an extremely dark, blurry or obstructed photograph with no identifiable subject',)
LABELS = WATER + NON_WATER + OBSCURED


def result(status, reason, score=None, **evidence):
    return dict(status=status, reason=reason, visibility_score=score,
                model=MODEL, model_revision=REVISION, method=METHOD, **evidence)


def pending():
    return result(REVIEW, 'This photo predates water validation. Run validation on the original capture.')


def eligible_image(observation):
    return not observation.get('ground') or (observation.get('water_validation') or {}).get('status') == VALID


@lru_cache(maxsize=1)
def detector():
    from transformers import CLIPModel, CLIPProcessor

    bundled_path = Path(__file__).resolve().parents[1] / 'models' / 'water-clip'
    directory = os.environ.get('AQUALENS_WATER_MODEL_DIR') or (
        bundled_path if (bundled_path / 'config.json').is_file() else None
    )
    source = str(Path(directory).resolve()) if directory else MODEL
    if directory and not Path(source, 'config.json').is_file():
        raise OSError(f'Water detector config.json is missing from {source}')
    options = {'local_files_only': True}
    if not directory:
        options['revision'] = REVISION
    model = CLIPModel.from_pretrained(source, **options,
                                     weights_only=True).eval()
    processor = CLIPProcessor.from_pretrained(source, use_fast=False, **options)
    return model, processor


def validate_water(decoded):
    height, width = decoded.shape[:2]
    scale = min(1, 256 / max(height, width))
    reduced = cv2.resize(decoded, (max(1, round(width * scale)), max(1, round(height * scale))),
                         interpolation=cv2.INTER_AREA)
    grey = cv2.cvtColor(reduced, cv2.COLOR_BGR2GRAY)
    dark = float(np.mean(grey <= 16))
    bright = float(np.mean(grey >= 250))
    exposure = 1 - max(dark, bright)
    if min(width, height) < 96 or exposure < 0.08:
        return result('INSUFFICIENT_VISIBILITY', 'The photo is too small or almost entirely underexposed or overexposed. Retake it with the water visible.')

    try:
        from PIL import Image
        import torch

        image = Image.fromarray(cv2.cvtColor(decoded, cv2.COLOR_BGR2RGB))
        model, processor = detector()
        inputs = processor(text=[f'This photograph shows {label}.' for label in LABELS],
                           images=image, padding=True, return_tensors='pt')
        with torch.inference_mode():
            probabilities = model(**inputs).logits_per_image.softmax(dim=-1)[0].tolist()
        scores = dict(zip(LABELS, probabilities, strict=True))
        water = sum(scores[label] for label in WATER)
        non_water = sum(scores[label] for label in NON_WATER)
        obscured = scores[OBSCURED[0]]
        if not all(np.isfinite(value) and 0 <= value <= 1 for value in scores.values()):
            raise ValueError('Invalid CLIP scores')
    except Exception:
        logging.getLogger(__name__).exception('Water screening inference unavailable')
        return result(REVIEW, 'The detector is unavailable. This photo is held for validation.')

    evidence = dict(water_model_score=round(water, 4), exposure_factor=round(exposure, 4),
                    top_match=max(scores, key=scores.get))
    if obscured >= 0.50:
        return result('INSUFFICIENT_VISIBILITY', 'The subject is obscured. Retake with the water surface or fill line clearly visible.', **evidence)
    if non_water >= 0.75 and water <= 0.20:
        return result('NO_WATER_DETECTED', f'The photo most closely matches {evidence["top_match"]}. Retake with the water visible.', **evidence)
    # A strong individual match can identify a clear sample even when the
    # competing glass and indoor prompts split the scene-level evidence.
    best_water = max(scores[label] for label in WATER)
    best_alternative = max(scores[label] for label in NON_WATER + OBSCURED)
    clear_container = (
        evidence['top_match'] in WATER[1:4]
        and water >= 0.45 and best_water >= 1.10 * best_alternative
    )
    if exposure >= 0.45 and (water >= 0.67 or clear_container):
        grade = visibility_grade(grey, exposure, water, scores)
        return result(VALID, 'The detector found a visible water body or sample.', grade, **evidence)
    return result(REVIEW, 'The detector could not confidently distinguish water from other content. Retake with the water surface or fill line in view.', **evidence)


def visibility_grade(grey, exposure, water, scores):
    """Grade visible detail using the central image region and appearance cues."""
    height, width = grey.shape
    region = grey[height // 5:height - height // 5, width // 5:width - width // 5]
    low, high = np.percentile(region, [10, 90])
    contrast = min(float(high - low) / 100, 1)
    detail = min(float(cv2.Laplacian(region, cv2.CV_32F).var()) / 250, 1)
    opaque_support = (scores[WATER[-2]] + scores[WATER[-1]]) / water
    clarity = (0.40 * contrast + 0.35 * detail + 0.25 * exposure) * (1 - 0.65 * opaque_support)
    return 1 + sum(clarity >= boundary for boundary in (0.20, 0.40, 0.60, 0.80))
