import React, { useState, useEffect } from "react";
import {
  Waves,
  LogOut,
  User,
  Activity,
  Fingerprint,
  FileText,
  TrendingUp,
  ShieldCheck,
  Home,
  AlertTriangle,
} from "lucide-react";
import { api } from "../../services/api";

export default function HeaderNav({ activePage, onNavigate, isDemoMode = false }) {
  const [currentUser, setCurrentUser] = useState(null);

  useEffect(() => {
    setCurrentUser(api.getCurrentUser());
  }, [activePage]);

  const handleLogout = () => {
    api.logout();
    setCurrentUser(null);
    onNavigate("landing");
  };

  const navLinks = [
    { id: "dashboard", label: "Overview", icon: Activity },
    { id: "fingerprint", label: "Water fingerprint", icon: Fingerprint },
    { id: "findings", label: "Detailed findings", icon: FileText },
    { id: "trends", label: "Trends & forecast", icon: TrendingUp },
    { id: "recommendations", label: "Recommendations", icon: ShieldCheck },
  ];

  return (
    <>
      <header className="dashboard-nav-container">
        <div className="dashboard-nav-inner">
          <div
            className="dashboard-brand-wrap"
            onClick={() => onNavigate("landing")}
            role="button"
            tabIndex={0}
            title="Return to AquaLens website"
          >
            <Waves size={22} color="#38bdf8" strokeWidth={1.8} />
            <div className="brand-titles">
              <span className="brand-name">
                AquaLens <small>AI</small>
              </span>
              <span className="brand-sub">Water Quality Monitoring</span>
            </div>
          </div>

          <nav className="dashboard-tab-links" aria-label="Dashboard navigation">
            {navLinks.map((item) => {
              const Icon = item.icon;
              const isActive = activePage === item.id;
              return (
                <button
                  key={item.id}
                  className={`dashboard-tab-btn ${isActive ? "is-active" : ""}`}
                  onClick={() => onNavigate(item.id)}
                >
                  <Icon size={14} />
                  <span>{item.label}</span>
                </button>
              );
            })}
          </nav>

          <div className="dashboard-nav-user-actions">
            <button
              className="home-return-btn"
              onClick={() => onNavigate("landing")}
              title="Return to AquaLens public website"
            >
              <Home size={14} />
              <span>Home</span>
            </button>

            {currentUser ? (
              <div className="user-profile-badge">
                <span className="user-badge-role">{currentUser.role || "Officer"}</span>
                <span className="user-badge-name">{currentUser.username}</span>
                <button
                  className="signout-btn"
                  onClick={handleLogout}
                  title="Sign out and return to home"
                >
                  <LogOut size={13} />
                  <span>Sign out</span>
                </button>
              </div>
            ) : (
              <button className="login-nav-btn" onClick={() => onNavigate("login")}>
                <User size={14} />
                <span>Sign in</span>
              </button>
            )}
          </div>
        </div>
      </header>

      {/* Persistent Demo Data Disclaimer Banner */}
      {isDemoMode && (
        <div className="demo-data-disclaimer-bar" role="status">
          <AlertTriangle size={14} className="demo-disclaimer-icon" />
          <span>
            <strong>DEMO DATA — illustrative only:</strong> You are viewing simulated development
            fixtures for testing the fingerprinting and anomaly pipeline. These do not represent active
            physical sampling stations.
          </span>
        </div>
      )}
    </>
  );
}
