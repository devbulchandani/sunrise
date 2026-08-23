import type { ReactNode } from "react";
import { Route, Routes } from "react-router-dom";
import { Header } from "./components/Header";
import { useEventStream } from "./hooks/useEventStream";
import MarketPulse from "./pages/MarketPulse";
import EventDetail from "./pages/EventDetail";
import Scrapers from "./pages/Scrapers";
import SystemPage from "./pages/System";

export default function App() {
  return (
    <AppChrome>
      <Routes>
        <Route path="/" element={<MarketPulse />} />
        <Route path="/events/:id" element={<EventDetail />} />
        <Route path="/scrapers" element={<Scrapers />} />
        <Route path="/system" element={<SystemPage />} />
        <Route path="*" element={<MarketPulse />} />
      </Routes>
    </AppChrome>
  );
}

/**
 * AppChrome owns an SSE connection for the header live dot. Pages open their
 * own handler-scoped subscriptions for data merging — SSE connections are
 * cheap and this keeps each page self-contained.
 */
function AppChrome({ children }: { children: ReactNode }) {
  const { status } = useEventStream({});
  return (
    <div className="flex min-h-screen flex-col">
      <Header streamStatus={status} />
      <main className="flex-1">{children}</main>
      <footer className="border-t border-edge px-5 py-4">
        <p className="mx-auto max-w-[1600px] font-mono text-[10px] uppercase tracking-widest text-ink-faint">
          Sunrise · autonomous financial intelligence · wake up before the market does
        </p>
      </footer>
    </div>
  );
}
