import React, { useState } from "react";
import { Waves, Lock, User, ArrowRight, AlertCircle, ArrowLeft } from "lucide-react";
import { api } from "../services/api";

export default function LoginPage({ onNavigate, redirectDestination = "dashboard", onLoginSuccess }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!username.trim() || !password) {
      setError("Please provide both username and password.");
      return;
    }

    setError(null);
    setLoading(true);

    try {
      await api.login(username.trim(), password);
      if (typeof onLoginSuccess === "function") {
        onLoginSuccess();
      }
      // Navigate to destination requested prior to login redirect
      onNavigate(redirectDestination || "dashboard");
    } catch (err) {
      setError(err.message || "Failed to authenticate. Please verify your credentials.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-page-container">
      <div className="login-card">
        <div className="login-brand-header">
          <div className="login-logo-mark">
            <Waves size={28} color="#38bdf8" strokeWidth={1.8} />
            <span className="login-logo-text">AquaLens AI</span>
          </div>
          <h1>Sign in to monitoring suite</h1>
          <p className="login-subtext">
            Enter your credentials to access water fingerprinting and station monitoring.
          </p>
        </div>

        {error && (
          <div className="login-error-banner" role="alert">
            <AlertCircle size={16} />
            <span>{error}</span>
          </div>
        )}

        <form onSubmit={handleSubmit} className="login-form" noValidate>
          <div className="form-field-group">
            <label htmlFor="login-username">Username or officer ID</label>
            <div className="input-with-icon">
              <User size={15} className="field-icon" />
              <input
                id="login-username"
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="Enter your username"
                autoComplete="username"
                disabled={loading}
                required
              />
            </div>
          </div>

          <div className="form-field-group">
            <label htmlFor="login-password">Password</label>
            <div className="input-with-icon">
              <Lock size={15} className="field-icon" />
              <input
                id="login-password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Enter your password"
                autoComplete="current-password"
                disabled={loading}
                required
              />
            </div>
          </div>

          <button type="submit" className="login-submit-btn" disabled={loading}>
            {loading ? "Verifying credentials..." : "Sign in to monitoring suite"}
            {!loading && <ArrowRight size={15} />}
          </button>
        </form>

        <div className="login-dev-guidance">
          <span className="dev-guidance-title">Development test account</span>
          <p>
            For local evaluation using the seeded development profile, sign in with:
            <br />
            <strong>Username:</strong> <code>admin</code> &nbsp;|&nbsp; <strong>Password:</strong>{" "}
            <code>AquaLens2026!</code>
          </p>
        </div>

        <div className="login-footer-actions">
          <button className="back-to-home-link" onClick={() => onNavigate("landing")}>
            <ArrowLeft size={14} />
            <span>Return to public website</span>
          </button>
        </div>
      </div>
    </div>
  );
}
