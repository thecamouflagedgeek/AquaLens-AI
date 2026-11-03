import React, { useState, useEffect } from "react";
import {
  MapPin,
  Clock,
  Upload,
  RefreshCw,
  ChevronRight,
  Database,
  Filter,
  Image as ImageIcon,
  AlertCircle,
  CheckCircle2,
  Info,
} from "lucide-react";
import HeaderNav from "../components/dashboard/HeaderNav";
import StationMap from "../components/dashboard/StationMap";
import { api } from "../services/api";

export default function DashboardPage({ onNavigate, selectedStationId: initialStationId }) {
  const [sources, setSources] = useState([]);
  const [stations, setStations] = useState([]);
  const [selectedStationId, setSelectedStationId] = useState(initialStationId || null);
  const [stationDetails, setStationDetails] = useState(null);
  const [observations, setObservations] = useState([]);
  const [labResults, setLabResults] = useState([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState(null);
  const [uploadSuccess, setUploadSuccess] = useState(null);

  // Station dataset view mode: "all", "registered" (is_demo === false), "demo" (is_demo === true)
  const [datasetMode, setDatasetMode] = useState("all");
  const [selectedRegion, setSelectedRegion] = useState("all");

  const loadInitialData = async () => {
    setLoading(true);
    setError(null);
    try {
      const [srcData, stData] = await Promise.all([api.getSources(), api.getStations()]);
      setSources(srcData);
      setStations(stData);

      if (stData.length > 0) {
        if (!selectedStationId || !stData.some((s) => s.id === selectedStationId)) {
          setSelectedStationId(stData[0].id);
        }
      } else {
        setSelectedStationId(null);
      }
    } catch (err) {
      setError(err.message || "Failed to load monitoring overview.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadInitialData();
  }, []);

  const loadStationDetails = async (stId) => {
    if (!stId) {
      setStationDetails(null);
      setObservations([]);
      setLabResults([]);
      return;
    }
    try {
      const [st, obsList, labs] = await Promise.all([
        api.getStation(stId),
        api.getStationObservations(stId, 10),
        api.getStationLabResults(stId).catch(() => []),
      ]);
      setStationDetails(st);
      setObservations(obsList);
      setLabResults(labs);
    } catch (err) {
      console.error("Error loading station details:", err);
    }
  };

  useEffect(() => {
    if (selectedStationId) {
      loadStationDetails(selectedStationId);
    }
  }, [selectedStationId]);

  const handleFileUpload = async (e) => {
    const file = e.target.files[0];
    if (!file || !selectedStationId) return;

    setUploading(true);
    setUploadSuccess(null);
    setError(null);

    const formData = new FormData();
    formData.append("station_id", selectedStationId);
    formData.append("image", file);
    formData.append("camera_model", "Field Inspection Camera v2");
    formData.append("illumination_condition", "Overcast");

    try {
      const newObs = await api.uploadObservation(formData);
      setUploadSuccess(`Observation #${newObs.id} analyzed and recorded successfully.`);
      await loadInitialData();
      await loadStationDetails(selectedStationId);
    } catch (err) {
      setError(err.message || "Upload and analysis failed.");
    } finally {
      setUploading(false);
    }
  };

  // Filter stations based on dataset mode and region
  const filteredStations = stations.filter((st) => {
    if (datasetMode === "registered" && st.is_demo === true) return false;
    if (datasetMode === "demo" && st.is_demo !== true) return false;
    if (selectedRegion !== "all") {
      const src = sources.find((s) => s.id === st.source_id);
      if (src && !src.region.toLowerCase().includes(selectedRegion.toLowerCase())) return false;
    }
    return true;
  });

  const selectedStation = stations.find((s) => s.id === selectedStationId);
  const isViewingDemo = selectedStation?.is_demo === true || datasetMode === "demo";
  const latestObs = observations.length > 0 ? observations[0] : null;

  return (
    <div className="dashboard-layout">
      <HeaderNav activePage="dashboard" onNavigate={onNavigate} isDemoMode={isViewingDemo} />

      <main className="dashboard-content-area">
        {/* Top Controls Bar */}
        <div className="dashboard-controls-bar">
          <div className="controls-heading">
            <h2>Monitoring overview</h2>
            <p className="controls-subtext">
              View registered water sources, spatial monitoring stations, and current visual condition.
            </p>
          </div>

          <div className="filter-group">
            {/* Dataset Mode Toggle */}
            <div className="dataset-toggle-group">
              <button
                type="button"
                className={`dataset-toggle-btn ${datasetMode === "all" ? "active" : ""}`}
                onClick={() => setDatasetMode("all")}
              >
                All stations ({stations.length})
              </button>
              <button
                type="button"
                className={`dataset-toggle-btn ${datasetMode === "registered" ? "active" : ""}`}
                onClick={() => setDatasetMode("registered")}
              >
                Registered only ({stations.filter((s) => !s.is_demo).length})
              </button>
              <button
                type="button"
                className={`dataset-toggle-btn ${datasetMode === "demo" ? "active" : ""}`}
                onClick={() => setDatasetMode("demo")}
              >
                Demo fixtures ({stations.filter((s) => s.is_demo).length})
              </button>
            </div>

            <button className="refresh-btn" onClick={loadInitialData} title="Reload data">
              <RefreshCw size={13} />
              <span>Refresh</span>
            </button>
          </div>
        </div>

        {error && (
          <div className="dashboard-alert-banner is-error" role="alert">
            <AlertCircle size={15} />
            <span>{error}</span>
          </div>
        )}

        {uploadSuccess && (
          <div className="dashboard-alert-banner is-success" role="status">
            <CheckCircle2 size={15} />
            <span>{uploadSuccess}</span>
          </div>
        )}

        {/* Main Grid: Map & Stations on Left, Station Details on Right */}
        <div className="dashboard-main-grid">
          {/* Left Column: Spatial Map & Station List */}
          <div className="dashboard-col-left">
            <div className="dashboard-card map-card">
              <div className="card-header">
                <span className="card-title">
                  <MapPin size={16} color="#38bdf8" /> Monitoring locations
                </span>
                <span className="card-badge">{filteredStations.length} stations</span>
              </div>
              <div className="map-view-wrapper">
                <StationMap
                  stations={filteredStations}
                  selectedStationId={selectedStationId}
                  onSelectStation={(id) => setSelectedStationId(id)}
                />
              </div>
            </div>

            <div className="dashboard-card station-list-card">
              <div className="card-header">
                <span className="card-title">
                  <Database size={16} color="#38bdf8" /> Stations directory
                </span>
              </div>

              {filteredStations.length > 0 ? (
                <div className="station-rows-list">
                  {filteredStations.map((st) => {
                    const isSelected = st.id === selectedStationId;
                    const src = sources.find((s) => s.id === st.source_id);
                    return (
                      <div
                        key={st.id}
                        className={`station-row-item ${isSelected ? "is-selected" : ""}`}
                        onClick={() => setSelectedStationId(st.id)}
                        role="button"
                        tabIndex={0}
                      >
                        <div className="station-row-main">
                          <div className="station-title-line">
                            <strong>{st.name}</strong>
                            {st.is_demo && <span className="demo-badge-inline">DEMO</span>}
                          </div>
                          <small>
                            {st.station_code} · {src?.name || "Water source"}
                          </small>
                        </div>
                        <div className="station-row-status">
                          <span
                            className={`status-tag condition-${(
                              st.latest_condition || "none"
                            ).toLowerCase()}`}
                          >
                            {st.latest_condition ? `${st.latest_condition} condition` : "No samples"}
                          </span>
                          <ChevronRight size={15} opacity={0.5} />
                        </div>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <div className="empty-panel-state">
                  <p>No stations match the selected filter.</p>
                  <small>
                    {datasetMode === "registered"
                      ? "No genuine monitoring stations registered yet. Switch to Demo fixtures or register a new station."
                      : "No stations available."}
                  </small>
                </div>
              )}
            </div>
          </div>

          {/* Right Column: Station Status & Latest Sample */}
          <div className="dashboard-col-right">
            {stationDetails ? (
              <div className="dashboard-card station-detail-panel">
                <div className="panel-header">
                  <div>
                    <div className="station-header-top">
                      <span className="station-code-badge">{stationDetails.station_code}</span>
                      {stationDetails.is_demo && (
                        <span className="demo-badge-pill">DEMO FIXTURE — illustrative only</span>
                      )}
                    </div>
                    <h3 className="panel-station-title">{stationDetails.name}</h3>
                    <p className="panel-station-coords">
                      Latitude {stationDetails.latitude ?? "N/A"}°, Longitude{" "}
                      {stationDetails.longitude ?? "N/A"}° · Elevation{" "}
                      {stationDetails.elevation_m ?? "0"} m
                    </p>
                  </div>

                  <div className="upload-box-wrapper">
                    <label className={`upload-action-btn ${uploading ? "is-disabled" : ""}`}>
                      <Upload size={13} />
                      <span>{uploading ? "Analyzing sample..." : "Upload sample"}</span>
                      <input
                        type="file"
                        accept="image/*"
                        onChange={handleFileUpload}
                        disabled={uploading}
                        style={{ display: "none" }}
                      />
                    </label>
                  </div>
                </div>

                {/* Key Status Indicators */}
                <div className="station-metrics-summary">
                  <div className="metric-box">
                    <span className="metric-label">Visual classification</span>
                    <strong
                      className={`metric-value condition-${(
                        stationDetails.latest_condition || "none"
                      ).toLowerCase()}`}
                    >
                      {stationDetails.latest_condition || "Unclassified"}
                    </strong>
                    <span className="metric-hint">Objective 2 Random Forest</span>
                  </div>

                  <div className="metric-box">
                    <span className="metric-label">Water Health Score</span>
                    <strong className="metric-value">
                      {stationDetails.health_score !== null
                        ? `${stationDetails.health_score} / 100`
                        : "Unavailable"}
                    </strong>
                    <span className="metric-hint">
                      {stationDetails.health_score !== null
                        ? "Relative visual index"
                        : "Requires established baseline"}
                    </span>
                  </div>

                  <div className="metric-box">
                    <span className="metric-label">Baseline status</span>
                    <strong className="metric-value">
                      {stationDetails.baseline_status === "established"
                        ? "Established"
                        : "Not established"}
                    </strong>
                    <span className="metric-hint">Source-specific fingerprint</span>
                  </div>

                  <div className="metric-box">
                    <span className="metric-label">Change from baseline</span>
                    <strong
                      className={`metric-value anomaly-${(
                        stationDetails.anomaly_status || "none"
                      ).toLowerCase()}`}
                    >
                      {stationDetails.anomaly_status
                        ? stationDetails.anomaly_status.replace(/_/g, " ")
                        : "Unassessed"}
                    </strong>
                    <span className="metric-hint">Robust MAD deviation</span>
                  </div>
                </div>

                {/* Latest Sample Section */}
                <div className="latest-observation-card">
                  <div className="sub-header">
                    <span>Latest sample</span>
                    <span className="timestamp">
                      <Clock size={12} />
                      {latestObs
                        ? new Date(latestObs.sampling_timestamp).toLocaleString()
                        : "No samples recorded"}
                    </span>
                  </div>

                  {latestObs ? (
                    <div className="obs-media-grid">
                      <div className="obs-image-frame">
                        <img
                          src={api.getStaticImageUrl(latestObs.image_url)}
                          alt="Water observation sample"
                          onError={(e) => {
                            e.target.style.display = "none";
                          }}
                        />
                      </div>
                      <div className="obs-attributes-list">
                        <div className="attr-item">
                          <span>Illumination</span>
                          <strong>{latestObs.illumination_condition || "Standard / Overcast"}</strong>
                        </div>
                        <div className="attr-item">
                          <span>Acquisition device</span>
                          <strong>{latestObs.camera_model || "Station camera"}</strong>
                        </div>
                        {latestObs.classification && (
                          <div className="attr-item">
                            <span>Classifier output probabilities</span>
                            <div className="prob-bars">
                              {Object.entries(latestObs.classification.probabilities).map(
                                ([cls, p]) => (
                                  <div key={cls} className="prob-bar-row">
                                    <span>{cls}</span>
                                    <div className="prob-bar-track">
                                      <div
                                        className="prob-bar-fill"
                                        style={{ width: `${p * 100}%` }}
                                      ></div>
                                    </div>
                                    <small>{(p * 100).toFixed(1)}%</small>
                                  </div>
                                )
                              )}
                            </div>
                            <span className="prob-note">
                              Tree-vote distribution; describes visual condition, not chemical safety.
                            </span>
                          </div>
                        )}
                      </div>
                    </div>
                  ) : (
                    <div className="empty-observations-box">
                      <ImageIcon size={28} opacity={0.4} />
                      <p>No observations recorded yet for this station.</p>
                      <small>Upload an image using the button above to begin monitoring.</small>
                    </div>
                  )}
                </div>

                {/* Certified Laboratory Records (if available) */}
                <div className="laboratory-records-preview">
                  <div className="sub-header">
                    <span>Laboratory test results</span>
                    <span className="lab-badge">Physical grab samples</span>
                  </div>
                  {labResults.length > 0 ? (
                    <table className="lab-records-table">
                      <thead>
                        <tr>
                          <th>Date</th>
                          <th>Turbidity (NTU)</th>
                          <th>pH</th>
                          <th>DO (mg/L)</th>
                          <th>TSS (mg/L)</th>
                        </tr>
                      </thead>
                      <tbody>
                        {labResults.slice(0, 3).map((r) => (
                          <tr key={r.id}>
                            <td>{new Date(r.sample_timestamp).toLocaleDateString()}</td>
                            <td>{r.turbidity_ntu ?? "—"}</td>
                            <td>{r.ph ?? "—"}</td>
                            <td>{r.dissolved_oxygen_mg_l ?? "—"}</td>
                            <td>{r.tss_mg_l ?? "—"}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  ) : (
                    <p className="no-lab-notes">
                      No laboratory test results linked to this station. Visual monitoring is kept
                      separate from chemical laboratory assays.
                    </p>
                  )}
                </div>

                {/* Navigation links to detailed pages */}
                <div className="deep-dive-nav-grid">
                  <button className="deep-dive-btn" onClick={() => onNavigate("fingerprint", stationDetails.id)}>
                    <span>Inspect water fingerprint</span>
                    <ChevronRight size={14} />
                  </button>
                  <button className="deep-dive-btn" onClick={() => onNavigate("findings", stationDetails.id)}>
                    <span>View detailed findings</span>
                    <ChevronRight size={14} />
                  </button>
                  <button className="deep-dive-btn" onClick={() => onNavigate("trends", stationDetails.id)}>
                    <span>Trends and forecast</span>
                    <ChevronRight size={14} />
                  </button>
                  <button className="deep-dive-btn" onClick={() => onNavigate("recommendations", stationDetails.id)}>
                    <span>Recommended actions</span>
                    <ChevronRight size={14} />
                  </button>
                </div>
              </div>
            ) : (
              <div className="dashboard-card empty-station-selection">
                <p>Select a monitoring station to view its current condition and telemetry.</p>
              </div>
            )}
          </div>
        </div>
      </main>
    </div>
  );
}
