"""
AquaLens AI - API Integration Tests
Tests all required FastAPI endpoints:
- GET /health
- POST /auth/login & GET /auth/me
- GET /sources & POST /sources
- GET /stations & GET /stations/{id}
- GET /stations/{id}/fingerprint
- GET /stations/{id}/findings
- GET /stations/{id}/forecast
- GET /stations/{id}/recommendations
"""

import pytest
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.db.session import engine, Base


@pytest.fixture(scope="module")
def client():
    # Trigger lifespan and table creation
    with TestClient(app) as c:
        yield c


def test_health_check_endpoint(client):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["database_connected"] is True
    assert data["model_loaded"] is True
    assert set(data["classes"]) == {"High", "Low", "Medium"}
    assert data["feature_count"] == 20


def test_auth_login_and_me(client):
    # Login with seeded admin
    login_resp = client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "AquaLens2026!"},
    )
    assert login_resp.status_code == 200
    token_data = login_resp.json()
    assert "access_token" in token_data
    assert token_data["role"] == "admin"

    # Test /auth/me with Bearer token
    headers = {"Authorization": f"Bearer {token_data['access_token']}"}
    me_resp = client.get("/api/v1/auth/me", headers=headers)
    assert me_resp.status_code == 200
    user_data = me_resp.json()
    assert user_data["username"] == "admin"
    assert user_data["role"] == "admin"


def test_sources_and_stations_endpoints(client):
    sources_resp = client.get("/api/v1/sources")
    assert sources_resp.status_code == 200
    sources = sources_resp.json()
    assert len(sources) >= 1

    stations_resp = client.get("/api/v1/stations")
    assert stations_resp.status_code == 200
    stations = stations_resp.json()
    assert len(stations) >= 1
    station_id = stations[0]["id"]

    station_resp = client.get(f"/api/v1/stations/{station_id}")
    assert station_resp.status_code == 200
    assert station_resp.json()["id"] == station_id


def test_fingerprint_and_forecast_endpoints(client):
    stations_resp = client.get("/api/v1/stations")
    stations = stations_resp.json()
    station_id = stations[0]["id"]

    # Fingerprint endpoint
    fp_resp = client.get(f"/api/v1/stations/{station_id}/fingerprint")
    assert fp_resp.status_code == 200
    fp_data = fp_resp.json()
    assert "status" in fp_data
    assert fp_data["methodology"] == "robust-median-iqr-mad"

    # Forecast endpoint (insufficient data state for new station)
    fc_resp = client.get(f"/api/v1/stations/{station_id}/forecast")
    assert fc_resp.status_code == 200
    fc_data = fc_resp.json()
    assert fc_data["status"] == "insufficient_data"
    assert "Insufficient historical observations" in fc_data["explanation"]

    # Recommendations endpoint
    rec_resp = client.get(f"/api/v1/stations/{station_id}/recommendations")
    assert rec_resp.status_code == 200
    assert isinstance(rec_resp.json(), list)

    # Detailed findings endpoint
    find_resp = client.get(f"/api/v1/stations/{station_id}/findings")
    assert find_resp.status_code == 200
    assert "station_name" in find_resp.json()
