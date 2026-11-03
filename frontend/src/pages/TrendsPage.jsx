import React, { useState, useEffect } from "react";
import { TrendingUp, Clock, AlertCircle, ShieldAlert } from "lucide-react";
import HeaderNav from "../components/dashboard/HeaderNav";
import { api } from "../services/api";

export default function TrendsPage({ onNavigate, selectedStationId: initialStationId }) {
  const [stations, setStations] = useState([]);
  const [selectedStationId, setSelectedStationId] = useState(initialStationId || null);
  const [trends, setTrends] = useState(null);
  const [forecast, setForecast] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    async function init() {
      try {
        const stList = await api.getStations();
        setStations(stList);
        if (stList.length > 0 && !selectedStationId) {
          setSelectedStationId(stList[0].id);
        }
      } catch (err) {
        setError("Failed to load stations.");
      }
    }
    init();
  }, []);

  useEffect(() => {
    if (!selectedStationId) return;
    setLoading(true);
    setError(null);

    Promise.all([
      api.getStationTrends(selectedStationId),
      api.getStationForecast(selectedStationId, 7),
    ])
      .then(([trendData, forecastData]) => {
        setTrends(trendData);
        setForecast(forecastData);
      })
      .catch((err) => {
        setError(err.message || "Failed to load trends and forecast.");
      })
      .finally(() => setLoading(false));
  }, [selectedStationId]);

  const selectedStation = stations.find((s) => s.id === selectedStationId);
  const isDemo = selectedStation?.is_demo === true;

  return (
    <div className="dashboard-layout">
      <HeaderNav activePage="trends" onNavigate={onNavigate} isDemoMode={isDemo} />

      <main className="dashboard-content-area">
        {/* Controls Header */}
        <div className="dashboard-controls-bar">
          <div className="controls-heading">
            <h2>Historical trends & forecast</h2>
            <p className="controls-subtext">
              Track chronological sample observations over time and review validated predictive projections.
            </p>
          </div>

          <div className="filter-group">
            <div className="filter-pill">
              <label htmlFor="trends-station-select">Monitoring station:</label>
              <select
                id="trends-station-select"
                value={selectedStationId || ""}
                onChange={(e) => setSelectedStationId(Number(e.target.value))}
              >
                {stations.map((st) => (
                  <option key={st.id} value={st.id}>
                    {st.name} ({st.station_code}) {st.is_demo ? "[Demo]" : ""}
                  </option>
                ))}
              </select>
            </div>
          </div>
        </div>

        {error && (
          <div className="dashboard-alert-banner is-error" role="alert">
            <AlertCircle size={15} />
            <span>{error}</span>
          </div>
        )}

        {trends && (
          <div className="trends-main-layout">
            {/* Summary Metrics */}
            <div className="trends-meta-strip">
              <div className="meta-card">
                <span className="meta-label">Recorded observations</span>
                <strong className="meta-value">{trends.total_observations} samples</strong>
                <span className="meta-sub">Actual telemetry records</span>
              </div>

              <div className="meta-card">
                <span className="meta-label">First sample</span>
                <strong className="meta-value">
                  {trends.time_range_start
                    ? new Date(trends.time_range_start).toLocaleDateString()
                    : "—"}
                </strong>
                <span className="meta-sub">Historical start date</span>
              </div>

              <div className="meta-card">
                <span className="meta-label">Latest sample</span>
                <strong className="meta-value">
                  {trends.time_range_end
                    ? new Date(trends.time_range_end).toLocaleDateString()
                    : "—"}
                </strong>
                <span className="meta-sub">Most recent observation</span>
              </div>

              <div className="meta-card">
                <span className="meta-label">Forecast eligibility</span>
                <strong
                  className={`meta-value ${
                    forecast?.status === "completed" ? "status-established" : "status-insufficient"
                  }`}
                >
                  {forecast?.status === "completed" ? "Eligible" : "Insufficient data"}
                </strong>
                <span className="meta-sub">Requires ≥10 historical points</span>
              </div>
            </div>

            {/* Historical Observation Log */}
            <div className="dashboard-card">
              <div className="card-header">
                <span className="card-title">
                  <Clock size={15} color="#da8c60" /> Chronological observation log
                </span>
                <span className="card-badge">{trends.points.length} samples</span>
              </div>

              {trends.points.length > 0 ? (
                <div className="fingerprint-table-wrapper">
                  <table className="fingerprint-table">
                    <thead>
                      <tr>
                        <th>Sample ID</th>
                        <th>Sampling timestamp</th>
                        <th>Visual category</th>
                        <th>Water Health Score</th>
                        <th>Anomaly score</th>
                        <th>Texture variance</th>
                        <th>Colour cast (B-R)</th>
                        <th>Largest contour area</th>
                      </tr>
                    </thead>
                    <tbody>
                      {trends.points.map((p) => (
                        <tr key={p.observation_id}>
                          <td className="font-mono">#{p.observation_id}</td>
                          <td>{new Date(p.timestamp).toLocaleString()}</td>
                          <td>
                            <span
                              className={`status-tag condition-${p.predicted_condition.toLowerCase()}`}
                            >
                              {p.predicted_condition}
                            </span>
                          </td>
                          <td className="font-semibold">
                            {p.health_score !== null ? `${p.health_score} / 100` : "Unavailable"}
                          </td>
                          <td>{p.anomaly_score !== null ? p.anomaly_score.toFixed(3) : "—"}</td>
                          <td>
                            {p.texture_intensity_variance !== null
                              ? p.texture_intensity_variance.toFixed(1)
                              : "—"}
                          </td>
                          <td>
                            {p.colour_cast_blue_red !== null
                              ? p.colour_cast_blue_red.toFixed(2)
                              : "—"}
                          </td>
                          <td>
                            {p.largest_contour_area !== null
                              ? p.largest_contour_area.toFixed(1)
                              : "—"}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="empty-observations-box">
                  <p>No historical observations recorded for this station yet.</p>
                </div>
              )}
            </div>

            {/* Predictive Forecast Section */}
            <div className="dashboard-card forecast-card">
              <div className="card-header">
                <span className="card-title">
                  <TrendingUp size={15} color="#50b5e5" /> Time-series predictive forecast
                </span>
                <span className="card-badge">7-day horizon</span>
              </div>

              {forecast?.status === "insufficient_data" ? (
                <div className="insufficient-data-notice">
                  <ShieldAlert size={28} color="#da8c60" />
                  <h3>Forecasting unavailable: insufficient historical observations</h3>
                  <p>{forecast.explanation}</p>
                  <p className="subtext">
                    The Objective 2 Random Forest classifier is an instantaneous image-condition
                    classifier, not a time-series model. To maintain scientific integrity, AquaLens does
                    not draw fabricated forecast lines without sufficient verified historical telemetry.
                  </p>
                </div>
              ) : (
                <div className="forecast-active-wrapper">
                  <div className="forecast-metrics-strip">
                    <span>
                      Method: <strong>{forecast?.method}</strong>
                    </span>
                    <span>
                      Validation MAE: <strong>{forecast?.validation_metrics?.validation_mae}</strong>
                    </span>
                    <span>
                      Evaluation samples:{" "}
                      <strong>{forecast?.validation_metrics?.validation_samples}</strong>
                    </span>
                  </div>

                  <div className="fingerprint-table-wrapper">
                    <table className="fingerprint-table">
                      <thead>
                        <tr>
                          <th>Projection date</th>
                          <th>Predicted relative stability</th>
                          <th>Lower bound (95% CI)</th>
                          <th>Upper bound (95% CI)</th>
                        </tr>
                      </thead>
                      <tbody>
                        {forecast?.forecast_points.map((fp) => (
                          <tr key={fp.date}>
                            <td className="font-mono">{fp.date}</td>
                            <td className="font-semibold text-accent">
                              {fp.predicted_health_score} / 100
                            </td>
                            <td>{fp.uncertainty_lower}</td>
                            <td>{fp.uncertainty_upper}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
