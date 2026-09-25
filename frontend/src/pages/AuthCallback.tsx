import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../services/auth";

export default function AuthCallback() {
  const { completeSignIn } = useAuth();
  const navigate = useNavigate();
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    completeSignIn()
      .then(() => active && navigate("/", { replace: true }))
      .catch(() => active && setError("Sign-in could not be completed. Please try again."));
    return () => {
      active = false;
    };
  }, [completeSignIn, navigate]);

  return (
    <section className="auth-stage">
      <div className="auth-horizon" aria-hidden="true" />
      <div className="auth-content">
        <div className="auth-brand">
          <span className="auth-brand-mark" aria-hidden="true">
            <svg viewBox="0 0 32 32" fill="none">
              <path d="M5 22.5h22M8 19a8 8 0 0 1 16 0M16 5v4m-9.2.8 2.8 2.8m12.8-2.8-2.8 2.8" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
              <path d="m10 18 4-3 3 2 5-5" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </span>
          <span className="font-mono text-sm font-bold tracking-[0.28em] text-amber">SUNRISE</span>
        </div>

        <div className="auth-panel" aria-live="polite">
          <div className={error ? "auth-status-icon auth-status-error" : "auth-status-icon"}>
            {error ? (
              <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
                <path d="M12 8v4m0 4h.01M10.3 3.9 2.8 17a2 2 0 0 0 1.7 3h15a2 2 0 0 0 1.7-3l-7.5-13.1a2 2 0 0 0-3.4 0Z" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            ) : (
              <span className="auth-spinner" aria-hidden="true" />
            )}
          </div>

          <p className="label-caps">{error ? "SIGN-IN INTERRUPTED" : "SECURE AUTHENTICATION"}</p>
          <h1 className="mt-3 text-2xl font-semibold tracking-tight text-ink">
            {error ? "We couldn’t complete sign-in." : "Checking your session"}
          </h1>
          <p className="mt-3 max-w-sm text-sm leading-6 text-ink-dim">
            {error
              ? "Your account is safe. Return to Sunrise and try signing in again."
              : "Verifying your credentials and preparing your market pulse."}
          </p>

          {error ? (
            <Link to="/" className="auth-return-link">
              Back to Sunrise <span aria-hidden="true">↗</span>
            </Link>
          ) : (
            <div className="auth-secure-note">
              <span className="h-1.5 w-1.5 rounded-full bg-bull" />
              Encrypted connection · This usually takes a moment
            </div>
          )}
        </div>

        <p className="auth-footer">AUTONOMOUS FINANCIAL INTELLIGENCE <span>·</span> WAKE UP BEFORE THE MARKET DOES</p>
      </div>
    </section>
  );
}
