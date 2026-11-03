import React, { useState, useEffect } from "react";
import { ShieldCheck, AlertTriangle, CheckCircle, Wrench, Microscope, Eye, ArrowRight } from "lucide-react";
import HeaderNav from "../components/dashboard/HeaderNav";
import { api } from "../services/api";

export default function RecommendationsPage({ onNavigate, selectedStationId: initialStationId }) {
  const [stations, setStations] = useState([]);
  const [selectedStationId, setSelectedStationId] = useState(initialStationId || null);
  const [recommendations, setRecommendations] = useState([]);
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
      .getStationRecommendations(selectedStationId)
      .then((recs) => setRecommendations(recs))
      .catch((err) => setError(err.message || "Failed to load recommendations."))
      .finally(() => setLoading(false));
  }, [selectedStationId]);

  const selectedStation = stations.find((s) => s.id === selectedStationId);
  const isDemo = selectedStation?.is_demo === true;

  const getCategoryIcon = (category) => {
    switch (category) {
      case "AcquisitionCheck":
        return <Wrench size={16} color="#da8c60" />;
      case "LaboratoryVerification":
        return <Microscope size={16} color="#50b5e5" />;
      case "AnomalyInvestigation":
        return <AlertTriangle size={16} color="#e06c75" />;
      default:
        return <Eye size={16} color="#268278" />;
    }
  };

  return (
    <div className="dashboard-layout">
      <HeaderNav activePage="recommendations" onNavigate={onNavigate} isDemoMode={isDemo} />

      <main className="dashboard-content-area">
        {/* Controls Header */}
        <div className="dashboard-controls-bar">
          <div className="controls-heading">
            <h2>Recommended actions</h2>
            <p className="controls-subtext">
              Actionable inspection, physical sampling, and quality control steps derived from observation deviations.
            </p>
          </div>

          <div className="filter-group">
            <div className="filter-pill">
              <label htmlFor="recs-station-select">Monitoring station:</label>
              <select
                id="recs-station-select"
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

        <div className="recommendations-container">
          <div className="recs-intro-banner">
            <p>
              Recommendations are generated through <strong>deterministic, evidence-based rules</strong> derived
              from statistical departures against the station's historical baseline. Visual anomalies alone do not
              establish chemical toxicity or drinking-water potability; they guide physical verification and certified
              laboratory testing.
            </p>
          </div>

          {recommendations.length > 0 ? (
            <div className="recommendations-grid">
              {recommendations.map((rec) => (
                <div key={rec.id} className={`rec-card priority-${rec.priority}`}>
                  <div className="rec-card-header">
                    <div className="rec-icon-title">
                      {getCategoryIcon(rec.category)}
                      <div>
                        <span className="rec-category-tag">{rec.category}</span>
                        <h3 className="rec-title">{rec.title}</h3>
                      </div>
                    </div>
                    <span className={`priority-badge priority-${rec.priority}`}>
                      {rec.priority.charAt(0).toUpperCase() + rec.priority.slice(1)} priority
                    </span>
                  </div>

                  {/* 1. What was observed */}
                  <div className="rec-detail-row">
                    <strong className="rec-sub-heading">What was observed:</strong>
                    <p className="rec-desc">{rec.description}</p>
                  </div>

                  {/* 2. Why it matters (Hypothesis) */}
                  {rec.hypothesis && (
                    <div className="rec-hypothesis-box">
                      <strong className="rec-sub-heading">Why it matters for further investigation:</strong>
                      <p>{rec.hypothesis}</p>
                    </div>
                  )}

                  {/* 3. What to do next */}
                  {rec.action_items && rec.action_items.length > 0 && (
                    <div className="rec-actions-block">
                      <strong className="rec-sub-heading">Recommended next steps:</strong>
                      <ul className="actions-list">
                        {rec.action_items.map((item, idx) => (
                          <li key={idx}>
                            <ArrowRight size={13} className="action-arrow" />
                            <span>{item}</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              ))}
            </div>
          ) : (
            <div className="empty-observations-box">
              <CheckCircle size={32} color="#268278" />
              <h3>No active deviations or follow-up actions</h3>
              <p>
                Station visual characteristics conform to the established baseline reference ranges.
                Standard visual monitoring should continue as scheduled.
              </p>
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
