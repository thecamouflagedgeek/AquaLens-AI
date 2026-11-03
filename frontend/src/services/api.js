/**
 * AquaLens AI - API Client Service
 * Connects frontend dashboard pages to the FastAPI backend.
 * Handles token authentication, session validation, and error normalization.
 */

const API_BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:8000/api/v1";
const STATIC_BASE_URL = import.meta.env.VITE_STATIC_URL || "http://localhost:8000";

function getAuthHeaders() {
  const token = localStorage.getItem("aqualens_token");
  const headers = { "Content-Type": "application/json" };
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }
  return headers;
}

export const api = {
  getStaticImageUrl(path) {
    if (!path) return "";
    if (path.startsWith("http://") || path.startsWith("https://")) return path;
    return `${STATIC_BASE_URL}${path.startsWith("/") ? "" : "/"}${path}`;
  },

  // Auth
  async login(username, password) {
    let res;
    try {
      res = await fetch(`${API_BASE_URL}/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
      });
    } catch (networkErr) {
      throw new Error(
        "Unable to connect to the AquaLens backend server. Please verify the backend is running on http://localhost:8000."
      );
    }

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || "Authentication failed. Please verify your credentials.");
    }

    const data = await res.json();
    localStorage.setItem("aqualens_token", data.access_token);
    localStorage.setItem(
      "aqualens_user",
      JSON.stringify({ username: data.username, role: data.role })
    );
    return data;
  },

  logout() {
    localStorage.removeItem("aqualens_token");
    localStorage.removeItem("aqualens_user");
  },

  getToken() {
    return localStorage.getItem("aqualens_token");
  },

  getCurrentUser() {
    try {
      return JSON.parse(localStorage.getItem("aqualens_user"));
    } catch {
      return null;
    }
  },

  async getMe() {
    const token = localStorage.getItem("aqualens_token");
    if (!token) throw new Error("No active token found.");

    let res;
    try {
      res = await fetch(`${API_BASE_URL}/auth/me`, { headers: getAuthHeaders() });
    } catch (networkErr) {
      throw new Error("Unable to connect to authentication server.");
    }

    if (!res.ok) {
      this.logout();
      throw new Error("Session expired or invalid.");
    }

    const data = await res.json();
    localStorage.setItem(
      "aqualens_user",
      JSON.stringify({ username: data.username, role: data.role })
    );
    return data;
  },

  // Sources & Stations
  async getSources() {
    const res = await fetch(`${API_BASE_URL}/sources`);
    if (!res.ok) throw new Error("Failed to load water sources.");
    return res.json();
  },

  async getStations(sourceId = null, isDemo = null) {
    const params = new URLSearchParams();
    if (sourceId) params.append("source_id", sourceId);
    if (isDemo !== null) params.append("is_demo", isDemo);
    const qs = params.toString() ? `?${params.toString()}` : "";
    const res = await fetch(`${API_BASE_URL}/stations${qs}`);
    if (!res.ok) throw new Error("Failed to load monitoring stations.");
    return res.json();
  },

  async getStation(id) {
    const res = await fetch(`${API_BASE_URL}/stations/${id}`);
    if (!res.ok) throw new Error(`Station ${id} not found.`);
    return res.json();
  },

  // Observations
  async getStationObservations(stationId, limit = 50) {
    const res = await fetch(`${API_BASE_URL}/stations/${stationId}/observations?limit=${limit}`);
    if (!res.ok) throw new Error("Failed to load observations.");
    return res.json();
  },

  async uploadObservation(formData) {
    const token = localStorage.getItem("aqualens_token");
    const headers = {};
    if (token) headers["Authorization"] = `Bearer ${token}`;

    const res = await fetch(`${API_BASE_URL}/observations`, {
      method: "POST",
      headers,
      body: formData,
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || "Failed to upload and process observation.");
    }
    return res.json();
  },

  // Fingerprint (Baseline)
  async getStationFingerprint(stationId) {
    const res = await fetch(`${API_BASE_URL}/stations/${stationId}/fingerprint`);
    if (!res.ok) throw new Error("Failed to load fingerprint.");
    return res.json();
  },

  async buildStationFingerprint(stationId, minSamples = null) {
    const token = localStorage.getItem("aqualens_token");
    const headers = { "Content-Type": "application/json" };
    if (token) headers["Authorization"] = `Bearer ${token}`;

    const res = await fetch(`${API_BASE_URL}/stations/${stationId}/fingerprint/build`, {
      method: "POST",
      headers,
      body: JSON.stringify({ min_samples: minSamples }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || "Failed to recalculate baseline.");
    }
    return res.json();
  },

  // Anomaly & Health Score
  async getObservationAnomaly(observationId) {
    const res = await fetch(`${API_BASE_URL}/observations/${observationId}/anomaly`);
    if (!res.ok) throw new Error("Failed to load anomaly analysis.");
    return res.json();
  },

  async getObservationHealthScore(observationId) {
    const res = await fetch(`${API_BASE_URL}/observations/${observationId}/health-score`);
    if (!res.ok) throw new Error("Failed to load health score.");
    return res.json();
  },

  // Detailed Findings
  async getStationFindings(stationId) {
    const res = await fetch(`${API_BASE_URL}/stations/${stationId}/findings`);
    if (!res.ok) throw new Error("Failed to load station findings.");
    return res.json();
  },

  // Trends & Forecast
  async getStationTrends(stationId) {
    const res = await fetch(`${API_BASE_URL}/stations/${stationId}/trends`);
    if (!res.ok) throw new Error("Failed to load historical trends.");
    return res.json();
  },

  async getStationForecast(stationId, horizonDays = 7) {
    const res = await fetch(
      `${API_BASE_URL}/stations/${stationId}/forecast?horizon_days=${horizonDays}`
    );
    if (!res.ok) throw new Error("Failed to load station forecast.");
    return res.json();
  },

  // Recommendations
  async getStationRecommendations(stationId) {
    const res = await fetch(`${API_BASE_URL}/stations/${stationId}/recommendations`);
    if (!res.ok) throw new Error("Failed to load recommendations.");
    return res.json();
  },

  // Laboratory Results
  async getStationLabResults(stationId) {
    const res = await fetch(`${API_BASE_URL}/stations/${stationId}/laboratory-results`);
    if (!res.ok) throw new Error("Failed to load laboratory results.");
    return res.json();
  },
};
