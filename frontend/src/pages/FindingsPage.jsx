import React, { useState, useEffect } from "react";
import { ArrowRight, AlertTriangle, ShieldCheck, Info } from "lucide-react";
import HeaderNav from "../components/dashboard/HeaderNav";
import { api } from "../services/api";

export default function FindingsPage({ onNavigate, selectedStationId: initialStationId }) {
  const [stations, setStations] = useState([]);
  const [selectedStationId, setSelectedStationId] = useState(initialStationId || null);
  const [findings, setFindings] = useState(null);
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
    api
      .getStationFindings(selectedStationId)
      .then((data) => setFindings(data))
      .catch((err) => setError(err.message || "Failed to load detailed findings."))
      .finally(() => setLoading(false));
  }, [selectedStationId]);

  const selectedStation = stations.find((s) => s.id === selectedStationId);
  const isDemo = selectedStation?.is_demo === true;

  return (
    <div className="dashboard-layout">
      <HeaderNav activePage="findings" onNavigate={onNavigate} isDemoMode={isDemo} />

      <main className="dashboard-content-area">
        {/* Controls Header */}
        <div className="dashboard-controls-bar">
          <div className="controls-heading">
            <h2>Detailed findings</h2>
            <p className="controls-subtext">
              Examine what changed between recent observations and compare against the station reference fingerprint.
            </p>
          </div>

          <div className="filter-group">
            <div className="filter-pill">
              <label htmlFor="findings-station-select">Monitoring station:</label>
              <select
                id="findings-station-select"
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
            <AlertTriangle size={15} />
            <span>{error}</span>
          </div>
        )}

        {findings && (
          <div className="findings-main-layout">
            {!findings.has_data ? (
              <div className="insufficient-data-notice">
                <AlertTriangle size={28} color="#da8c60" />
                <h3>No observation history recorded</h3>
                <p>
                  At least one observation sample must be uploaded to generate comparative findings for this station.
                </p>
                <button className="orange-button" onClick={() => onNavigate("dashboard")}>
                  Upload observation sample
                </button>
              </div>
            ) : (
              <>
                {/* Section 1: Sample Comparison */}
                <div className="dashboard-card visual-comparison-card">
                  <div className="card-header">
                    <span className="card-title">Sample comparison</span>
                    <span className="card-badge">Recent observations</span>
                  </div>

                  <div className="comparison-images-grid">
                    {/* Previous Observation */}
                    <div className="image-comparison-col">
                      <div className="col-label">
                        <span>Previous sample</span>
                        {findings.previous_observation && (
                          <small>
                            {new Date(findings.previous_observation.timestamp).toLocaleString()}
                          </small>
                        )}
                      </div>
                      <div className="comparison-image-container">
                        {findings.previous_observation?.image_url ? (
                          <img
                            src={api.getStaticImageUrl(findings.previous_observation.image_url)}
                            alt="Previous observation sample"
                            onError={(e) => {
                              e.target.style.display = "none";
                            }}
                          />
                        ) : (
                          <div className="empty-photo-placeholder">
                            No prior observation on record
                          </div>
                        )}
                      </div>
                      {findings.previous_observation && (
                        <div className="col-meta-box">
                          <span>
                            Visual category:{" "}
                            <strong>{findings.previous_observation.predicted_condition}</strong>
                          </span>
                        </div>
                      )}
                    </div>

                    <div className="comparison-divider-col">
                      <ArrowRight size={20} color="#da8c60" />
                    </div>

                    {/* Current Observation */}
                    <div className="image-comparison-col">
                      <div className="col-label is-current">
                        <span>Latest sample</span>
                        <small>
                          {new Date(findings.current_observation.timestamp).toLocaleString()}
                        </small>
                      </div>
                      <div className="comparison-image-container is-current">
                        <img
                          src={api.getStaticImageUrl(findings.current_observation.image_url)}
                          alt="Latest observation sample"
                          onError={(e) => {
                            e.target.style.display = "none";
                          }}
                        />
                      </div>
                      <div className="col-meta-box">
                        <span>
                          Visual category:{" "}
                          <strong>{findings.current_observation.predicted_condition}</strong>
                        </span>
                        <span>
                          Baseline deviation:{" "}
                          <strong>
                            {findings.current_observation.anomaly_status?.replace(/_/g, " ")}
                          </strong>
                        </span>
                        <span>
                          Health score:{" "}
                          <strong>
                            {findings.current_observation.health_score !== null
                              ? `${findings.current_observation.health_score}/100`
                              : "Unavailable"}
                          </strong>
                        </span>
                      </div>
                    </div>
                  </div>
                </div>

                {/* Section 2: Features with Largest Deviations */}
                <div className="dashboard-card">
                  <div className="card-header">
                    <span className="card-title">
                      <ShieldCheck size={15} color="#50b5e5" /> Features with largest deviations
                    </span>
                    <span className="card-badge">Empirical observations</span>
                  </div>
                  <div className="grounded-findings-list">
                    {findings.grounded_findings.map((finding, idx) => (
                      <div key={idx} className="finding-item-row">
                        <div className="finding-bullet" />
                        <p>{finding}</p>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Section 3: How to Interpret These Results */}
                <div className="dashboard-card">
                  <div className="card-header">
                    <span className="card-title">
                      <Info size={15} color="#da8c60" /> How to interpret these results
                    </span>
                  </div>
                  <div className="distinction-grid">
                    <div className="distinction-box">
                      <strong>Global visual category (Random Forest)</strong>
                      <p>
                        Classifies overall visual turbidity into Low, Medium, or High condition
                        based on the global model trained on 6,515 water images.
                      </p>
                    </div>
                    <div className="distinction-box">
                      <strong>Source anomaly assessment</strong>
                      <p>
                        Evaluates whether this observation departs significantly from this specific
                        station's historical optical baseline.
                      </p>
                    </div>
                    <div className="distinction-box">
                      <strong>Recent step change</strong>
                      <p>
                        Measures the direct numerical difference between the latest sample and the
                        immediately preceding observation.
                      </p>
                    </div>
                  </div>
                </div>

                {/* Section 4: Detailed Comparison Table */}
                <div className="dashboard-card">
                  <div className="card-header">
                    <span className="card-title">Detailed descriptor comparison</span>
                    <span className="card-badge">20 features</span>
                  </div>
                  <div className="fingerprint-table-wrapper">
                    <table className="fingerprint-table">
                      <thead>
                        <tr>
                          <th>Descriptor</th>
                          <th>Latest value</th>
                          <th>Previous value</th>
                          <th>Station baseline median</th>
                          <th>Change from previous</th>
                          <th>Change from baseline</th>
                        </tr>
                      </thead>
                      <tbody>
                        {findings.comparison_table.map((row) => (
                          <tr key={row.feature}>
                            <td className="font-mono">{row.feature}</td>
                            <td className="font-semibold">{row.current_value.toFixed(4)}</td>
                            <td>
                              {row.previous_value !== null ? row.previous_value.toFixed(4) : "—"}
                            </td>
                            <td>
                              {row.baseline_median !== null ? row.baseline_median.toFixed(4) : "—"}
                            </td>
                            <td>
                              {row.delta_from_previous !== null ? (
                                <span
                                  className={
                                    Math.abs(row.delta_from_previous) > 1
                                      ? "text-accent font-semibold"
                                      : ""
                                  }
                                >
                                  {row.delta_from_previous > 0 ? "+" : ""}
                                  {row.delta_from_previous.toFixed(4)}
                                </span>
                              ) : (
                                "—"
                              )}
                            </td>
                            <td>
                              {row.delta_from_baseline !== null ? (
                                <span
                                  className={
                                    Math.abs(row.delta_from_baseline) > 1
                                      ? "text-accent font-semibold"
                                      : ""
                                  }
                                >
                                  {row.delta_from_baseline > 0 ? "+" : ""}
                                  {row.delta_from_baseline.toFixed(4)}
                                </span>
                              ) : (
                                "—"
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              </>
            )}
          </div>
        )}
      </main>
    </div>
  );
}
