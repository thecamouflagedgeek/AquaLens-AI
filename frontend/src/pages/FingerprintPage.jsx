import React, { useState, useEffect } from "react";
import { Fingerprint, AlertCircle, RefreshCw, CheckCircle, HelpCircle, ArrowRight } from "lucide-react";
import HeaderNav from "../components/dashboard/HeaderNav";
import { api } from "../services/api";

const FEATURE_READABLE_NAMES = {
  lab_a_min: "CIELAB a* minimum (green-red axis)",
  rgb_2_median: "Green channel median intensity",
  colour_ratio_gb: "Green-to-blue channel ratio",
  rgb_3_median: "Blue channel median intensity",
  hsv_hue_median: "HSV dominant hue median",
  colour_ratio_rb: "Red-to-blue channel ratio",
  lab_a_std: "CIELAB a* standard deviation",
  hsv_saturation_max: "HSV saturation peak",
  lab_b_median: "CIELAB b* median (blue-yellow axis)",
  hsv_saturation_median: "HSV saturation median",
  lab_lightness_max: "CIELAB lightness maximum",
  colour_cast_blue_red: "Blue-red chromatic cast",
  rgb_3_max: "Blue channel maximum intensity",
  lab_b_max: "CIELAB b* maximum",
  texture_intensity_variance: "Grayscale texture intensity variance",
  largest_contour_area: "Largest structural contour area",
  contour_area_std: "Contour area standard deviation",
  component_area_mean: "Connected component mean area",
  component_area_std: "Connected component area variation",
  component_count: "Distinct particle / component count",
};

export default function FingerprintPage({ onNavigate, selectedStationId: initialStationId }) {
  const [stations, setStations] = useState([]);
  const [selectedStationId, setSelectedStationId] = useState(initialStationId || null);
  const [fingerprint, setFingerprint] = useState(null);
  const [latestObs, setLatestObs] = useState(null);
  const [loading, setLoading] = useState(true);
  const [rebuilding, setRebuilding] = useState(false);
  const [error, setError] = useState(null);
  const [message, setMessage] = useState(null);

  useEffect(() => {
    async function init() {
      try {
        const stList = await api.getStations();
        setStations(stList);
        if (stList.length > 0 && !selectedStationId) {
          setSelectedStationId(stList[0].id);
        }
      } catch (err) {
        setError("Failed to load monitoring stations.");
      }
    }
    init();
  }, []);

  const loadFingerprintData = async (stId) => {
    if (!stId) return;
    setLoading(true);
    setError(null);
    try {
      const [fp, obsList] = await Promise.all([
        api.getStationFingerprint(stId),
        api.getStationObservations(stId, 1),
      ]);
      setFingerprint(fp);
      setLatestObs(obsList.length > 0 ? obsList[0] : null);
    } catch (err) {
      setError(err.message || "Failed to load station fingerprint.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (selectedStationId) {
      loadFingerprintData(selectedStationId);
    }
  }, [selectedStationId]);

  const handleRebuild = async () => {
    if (!selectedStationId) return;
    setRebuilding(true);
    setMessage(null);
    setError(null);
    try {
      const updated = await api.buildStationFingerprint(selectedStationId);
      setFingerprint(updated);
      setMessage(
        updated.status === "established"
          ? `Baseline fingerprint successfully established (version ${updated.version}).`
          : `Insufficient observations: baseline cannot be established yet.`
      );
    } catch (err) {
      setError(err.message || "Recalculation failed.");
    } finally {
      setRebuilding(false);
    }
  };

  const selectedStation = stations.find((s) => s.id === selectedStationId);
  const isEstablished = fingerprint?.status === "established";
  const isDemo = selectedStation?.is_demo === true;

  return (
    <div className="dashboard-layout">
      <HeaderNav activePage="fingerprint" onNavigate={onNavigate} isDemoMode={isDemo} />

      <main className="dashboard-content-area">
        {/* Controls Header */}
        <div className="dashboard-controls-bar">
          <div className="controls-heading">
            <h2>Water fingerprint</h2>
            <p className="controls-subtext">
              Source-specific visual baseline profile capturing historical optical characteristics.
            </p>
          </div>

          <div className="filter-group">
            <div className="filter-pill">
              <label htmlFor="fingerprint-station-select">Monitoring station:</label>
              <select
                id="fingerprint-station-select"
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

            <button
              className="action-button-accent"
              onClick={handleRebuild}
              disabled={rebuilding}
              title="Recalculate baseline using all eligible observations"
            >
              <RefreshCw size={13} className={rebuilding ? "spin-icon" : ""} />
              <span>{rebuilding ? "Calculating..." : "Recalculate baseline"}</span>
            </button>
          </div>
        </div>

        {error && (
          <div className="dashboard-alert-banner is-error" role="alert">
            <AlertCircle size={15} />
            <span>{error}</span>
          </div>
        )}

        {message && (
          <div className="dashboard-alert-banner is-success" role="status">
            <CheckCircle size={15} />
            <span>{message}</span>
          </div>
        )}

        {fingerprint && (
          <div className="fingerprint-main-container">
            {/* 4 Core Questions Summary Strip */}
            <div className="fingerprint-meta-grid">
              <div className="meta-card">
                <span className="meta-label">1. Baseline status</span>
                <strong
                  className={`meta-value ${
                    isEstablished ? "status-established" : "status-insufficient"
                  }`}
                >
                  {isEstablished ? "Established" : "Not established"}
                </strong>
                <span className="meta-sub">
                  {isEstablished ? `Version ${fingerprint.version}` : "Insufficient validated data"}
                </span>
              </div>

              <div className="meta-card">
                <span className="meta-label">2. Supporting samples</span>
                <strong className="meta-value">{fingerprint.sample_count} observations</strong>
                <span className="meta-sub">
                  {isEstablished ? "Satisfies ≥5 requirement" : "Requires at least 5 samples"}
                </span>
              </div>

              <div className="meta-card">
                <span className="meta-label">3. Reference period</span>
                <strong className="meta-value">
                  {fingerprint.start_date
                    ? `${new Date(fingerprint.start_date).toLocaleDateString()} — ${new Date(
                        fingerprint.end_date
                      ).toLocaleDateString()}`
                    : "None recorded"}
                </strong>
                <span className="meta-sub">Station chronological window</span>
              </div>

              <div className="meta-card">
                <span className="meta-label">4. Anomaly assessment</span>
                <strong className="meta-value">
                  {isEstablished
                    ? latestObs?.features
                      ? "Evaluated"
                      : "Awaiting sample"
                    : "Not yet assessable"}
                </strong>
                <span className="meta-sub">Robust MAD comparison</span>
              </div>
            </div>

            {/* If baseline not established: show clean, informative explanation */}
            {!isEstablished ? (
              <div className="insufficient-data-notice">
                <AlertCircle size={28} color="#da8c60" />
                <h3>Fingerprint not yet established</h3>
                <p>
                  AquaLens strictly enforces scientific data sufficiency: a baseline is never
                  fabricated from a single image or guessed. This station currently has{" "}
                  <strong>{fingerprint.sample_count}</strong> of the required{" "}
                  <strong>5</strong> validated reference observations.
                </p>
                <div className="insufficient-actions">
                  <button className="orange-button" onClick={() => onNavigate("dashboard")}>
                    Go to monitoring overview to upload samples
                  </button>
                </div>
              </div>
            ) : (
              <>
                {/* 20-Feature Comparison Table */}
                <div className="dashboard-card">
                  <div className="card-header">
                    <span className="card-title">
                      <Fingerprint size={15} color="#da8c60" /> Reference values and latest sample
                      comparison
                    </span>
                    <span className="card-badge">20 visual descriptors</span>
                  </div>

                  <div className="fingerprint-table-wrapper">
                    <table className="fingerprint-table">
                      <thead>
                        <tr>
                          <th>Descriptor</th>
                          <th>Technical key</th>
                          <th>Latest sample</th>
                          <th>Baseline median</th>
                          <th>Interquartile range (IQR)</th>
                          <th>MAD dispersion</th>
                          <th>Reference bounds</th>
                          <th>Difference</th>
                        </tr>
                      </thead>
                      <tbody>
                        {Object.entries(fingerprint.stats).map(([featName, stat]) => {
                          const curVal = latestObs?.features ? latestObs.features[featName] : null;
                          const diff =
                            curVal !== null && stat.median !== undefined ? curVal - stat.median : null;
                          const isAbove = diff !== null && diff > stat.mad * 2;
                          const isBelow = diff !== null && diff < -stat.mad * 2;

                          return (
                            <tr key={featName} className={isAbove || isBelow ? "row-deviated" : ""}>
                              <td className="font-semibold">
                                {FEATURE_READABLE_NAMES[featName] || featName}
                              </td>
                              <td className="font-mono">{featName}</td>
                              <td className="font-semibold">
                                {curVal !== null ? curVal.toFixed(4) : "—"}
                              </td>
                              <td>{stat.median.toFixed(4)}</td>
                              <td>{stat.iqr.toFixed(4)}</td>
                              <td>{stat.mad.toFixed(4)}</td>
                              <td className="text-muted">
                                [{stat.min.toFixed(3)} — {stat.max.toFixed(3)}]
                              </td>
                              <td>
                                {diff !== null ? (
                                  <span
                                    className={`delta-tag ${
                                      isAbove ? "delta-high" : isBelow ? "delta-low" : "delta-normal"
                                    }`}
                                  >
                                    {diff > 0 ? "+" : ""}
                                    {diff.toFixed(3)}
                                  </span>
                                ) : (
                                  "—"
                                )}
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                </div>

                {/* Plain-English Methodology Section */}
                <div className="dashboard-card limitations-card">
                  <div className="card-header">
                    <span className="card-title">
                      <HelpCircle size={15} color="#50b5e5" /> How to interpret these results
                    </span>
                  </div>
                  <div className="limitations-content">
                    <p>
                      <strong>Why source-specific baselines?</strong> Natural water bodies possess
                      unique visual baselines caused by regional geology, local vegetation tannins,
                      and seasonal water flow. Comparing an alpine lake against an estuary using a
                      single universal threshold creates false alarms. AquaLens tracks changes
                      relative to each station's own historical reference profile.
                    </p>
                    <p>
                      <strong>Robust statistics:</strong> Median and Median Absolute Deviation (MAD)
                      are used instead of standard mean and standard deviation because they resist
                      distortion from occasional acquisition anomalies or extreme weather events.
                    </p>
                    <p className="disclaimer-text">
                      Note: Visual deviations describe optical characteristics (such as turbidity,
                      colour cast, or surface turbulence). They do not establish chemical potability
                      or certified drinking-water safety.
                    </p>
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
