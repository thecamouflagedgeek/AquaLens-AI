"""Location-driven satellite acquisition and historical monitoring.

Deliberately independent of the camera-image pipeline:

- no import of ``ml.feature_schema`` / ``FEATURE_NAMES``
- no import of ``services.fingerprint_service`` / ``services.anomaly_service``
- satellite metrics never enter ``feature_vectors``

The public seams are ``aoi`` (geometry), ``indices`` (spectral logic),
``gee`` (Earth Engine transport), ``service`` (orchestration/persistence)
and ``api.satellite`` (HTTP).
"""
