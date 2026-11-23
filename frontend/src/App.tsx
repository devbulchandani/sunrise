import { lazy, Suspense, useEffect, useState } from "react";
import { Link, Route, Routes, useLocation } from "react-router-dom";
import { Header } from "./components/Header";
import { CommandPalette } from "./components/CommandPalette";
import { SunriseMark, External, ArrowUpRight } from "./components/icons";
import { useEventStream } from "./hooks/useEventStream";
import MarketPulse from "./pages/MarketPulse";
import { Spinner } from "./components/ui";

const EventDetail = lazy(() => import("./pages/EventDetail"));
const Scrapers = lazy(() => import("./pages/Scrapers"));
const SystemPage = lazy(() => import("./pages/System"));
const Trading = lazy(() => import("./pages/Trading"));
const AuthCallback = lazy(() => import("./pages/AuthCallback"));

function ScrollToTop() {
  const { pathname } = useLocation();
  useEffect(() => {
    window.scrollTo({ top: 0, behavior: "auto" });
  }, [pathname]);
  return null;
}

export default function App() {
  return (
    <AppChrome>
      <ScrollToTop />
      <Suspense fallback={<RouteFallback />}>
        <Routes>
          <Route path="/" element={<MarketPulse />} />
          <Route path="/events/:id" element={<EventDetail />} />
          <Route path="/scrapers" element={<Scrapers />} />
          <Route path="/system" element={<SystemPage />} />
          <Route path="/trading" element={<Trading />} />
          <Route path="/auth/callback" element={<AuthCallback />} />
          <Route path="*" element={<MarketPulse />} />
        </Routes>
      </Suspense>
    </AppChrome>
  );
}

function AppChrome({ children }: { children: React.ReactNode }) {
  const { status } = useEventStream({});
  const [commandOpen, setCommandOpen] = useState(false);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setCommandOpen((open) => !open);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  return (
    <div className="relative flex min-h-[100dvh] flex-col">
      <a href="#main" className="skip-link">
        Skip to content
      </a>
      <div
        className="pointer-events-none fixed inset-0 -z-10 bg-grid bg-[size:72px_72px] opacity-[0.35] [mask-image:radial-gradient(75%_55%_at_50%_0%,#000,transparent)]"
        aria-hidden="true"
      />
      <Header streamStatus={status} onOpenCommand={() => setCommandOpen(true)} />
      <main id="main" className="flex-1 animate-fade">
        {children}
      </main>
      <Footer />
      <CommandPalette open={commandOpen} onClose={() => setCommandOpen(false)} />
    </div>
  );
}

function RouteFallback() {
  return (
    <div className="flex min-h-[70vh] items-center justify-center gap-3 text-xs text-ink-faint">
      <Spinner /> Opening the desk…
    </div>
  );
}

function Footer() {
  return (
    <footer className="mt-16 border-t border-edge/80 bg-base-soft/60">
      <div className="mx-auto max-w-[1600px] px-5 py-10">
        <div className="flex flex-col gap-8 md:flex-row md:items-start md:justify-between">
          <div className="max-w-sm">
            <Link to="/" className="flex items-center gap-2.5 text-ink">
              <SunriseMark className="h-5 w-5 text-amber" />
              <span className="font-mono text-xs font-bold tracking-[0.24em]">SUNRISE</span>
            </Link>
            <p className="mt-3 text-xs leading-5 text-ink-faint">
              An autonomous read on public financial news. Fact and interpretation are
              separated; every alert is labelled AI output, never financial advice.
            </p>
          </div>
          <div className="grid grid-cols-2 gap-8 sm:grid-cols-3">
            <div>
              <p className="label mb-3">Desk</p>
              <ul className="space-y-2 text-xs text-ink-dim">
                <li><Link className="link-underline" to="/">Market pulse</Link></li>
                <li><Link className="link-underline" to="/scrapers">Collector health</Link></li>
                <li><Link className="link-underline" to="/trading">Paper desk</Link></li>
                <li><Link className="link-underline" to="/system">Operations</Link></li>
              </ul>
            </div>
            <div>
              <p className="label mb-3">Signals</p>
              <ul className="space-y-2 text-xs text-ink-dim">
                <li>
                  <a className="link-underline inline-flex items-center gap-1" href="https://t.me/sunrisescraperbot" target="_blank" rel="noreferrer">
                    Telegram bot <External className="h-3 w-3" />
                  </a>
                </li>
                <li>
                  <a className="link-underline inline-flex items-center gap-1" href="https://github.com/devbulchandani/sunrise" target="_blank" rel="noreferrer">
                    Source <External className="h-3 w-3" />
                  </a>
                </li>
                <li>
                  <a className="link-underline inline-flex items-center gap-1" href="https://sunrise-api-proxy.devbulchandani876.workers.dev/api/health" target="_blank" rel="noreferrer">
                    API status <External className="h-3 w-3" />
                  </a>
                </li>
              </ul>
            </div>
            <div>
              <p className="label mb-3">Note</p>
              <p className="text-xs leading-5 text-ink-faint">
                AI interpretation may be wrong. Verify before acting.
              </p>
              <Link
                to="/system"
                className="mt-3 inline-flex items-center gap-1 text-[11px] text-amber transition-colors hover:text-[#ffc25c]"
              >
                Read the machine <ArrowUpRight className="h-3 w-3" />
              </Link>
            </div>
          </div>
        </div>
        <div className="mt-10 flex flex-col gap-2 border-t border-edge/70 pt-5 font-mono text-[10px] uppercase tracking-[0.14em] text-ink-faint sm:flex-row sm:items-center sm:justify-between">
          <span>© 2026 Sunrise · Wake up before the market does</span>
          <span>Signal, not noise</span>
        </div>
      </div>
    </footer>
  );
}
