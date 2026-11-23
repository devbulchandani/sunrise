import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { takePostLoginPath, useAuth } from "../services/auth";
import { AlertTriangle, ArrowRight, Shield, SunriseMark } from "../components/icons";
import { Button, Panel, Pill } from "../components/ui";

export default function AuthCallback() {
  const { completeSignIn } = useAuth();
  const navigate = useNavigate();
  const [error, setError] = useState("");
  // React 18 StrictMode replays effects in development; the authorization code
  // can only be exchanged once, so never start the exchange twice.
  const started = useRef(false);

  useEffect(() => {
    if (started.current) return;
    started.current = true;
    completeSignIn()
      .then(() => {
        navigate(takePostLoginPath() ?? "/", { replace: true });
      })
      .catch(() => {
        setError("Sign-in could not be completed. Please try again.");
      });
  }, [completeSignIn, navigate]);

  return (
    <section className="relative flex min-h-[calc(100dvh-4rem)] items-center justify-center overflow-hidden px-5 py-16">
      <div className="pointer-events-none absolute inset-0 bg-dawn" aria-hidden="true" />
      <div className="pointer-events-none absolute inset-0 grid-lines opacity-50" aria-hidden="true" />
      <div className="relative w-full max-w-md text-center">
        <Link to="/" className="mb-10 inline-flex items-center gap-2.5 text-ink">
          <span className="flex h-9 w-9 items-center justify-center rounded-xl border border-amber/25 bg-amber/[0.08] text-amber">
            <SunriseMark className="h-5 w-5" />
          </span>
          <span className="font-mono text-sm font-bold tracking-[0.24em]">SUNRISE</span>
        </Link>

        <Panel className="px-7 py-9 sm:px-10 sm:py-11">
          <div
            className={`mx-auto mb-6 flex h-12 w-12 items-center justify-center rounded-full border ${
              error
                ? "border-bear/30 bg-bear/10 text-bear"
                : "border-amber/25 bg-amber/[0.08] text-amber"
            }`}
            aria-hidden="true"
          >
            {error ? (
              <AlertTriangle className="h-5 w-5" />
            ) : (
              <span className="h-5 w-5 animate-spin rounded-full border-2 border-amber/25 border-t-amber" />
            )}
          </div>

          <Pill tone={error ? "bear" : "amber"}>
            {error ? "Sign-in interrupted" : "Secure authentication"}
          </Pill>

          <h1 className="display mt-4 text-3xl leading-tight text-ink">
            {error ? "We couldn’t finish signing you in." : "Checking your session"}
          </h1>
          <p className="mx-auto mt-3 max-w-sm text-sm leading-6 text-ink-dim">
            {error
              ? "Your account is safe. Return to Sunrise and start the sign-in flow again."
              : "Verifying your credentials and preparing your desk."}
          </p>

          <div className="mt-7">
            {error ? (
              <Link to="/">
                <Button variant="primary" className="w-full">
                  Back to Sunrise
                  <ArrowRight className="h-4 w-4" />
                </Button>
              </Link>
            ) : (
              <p className="flex items-center justify-center gap-2 font-mono text-[10px] uppercase tracking-[0.14em] text-ink-faint">
                <Shield className="h-3.5 w-3.5 text-bull" />
                Encrypted connection · usually a moment
              </p>
            )}
          </div>
        </Panel>

        <p className="mt-8 font-mono text-[9px] uppercase tracking-[0.18em] text-ink-faint">
          Autonomous market intelligence <span className="text-amber/60">·</span> wake up
          before the market does
        </p>
      </div>
    </section>
  );
}
