import { Link, useLocation } from "react-router-dom";
import { LiveDot } from "./StatusDot";
import type { StreamStatus } from "../hooks/useEventStream";

const NAV = [
  { to: "/", label: "Market Pulse" },
  { to: "/scrapers", label: "Scraper Health" },
  { to: "/system", label: "System" },
];

export function Header({ streamStatus }: { streamStatus: StreamStatus }) {
  const { pathname } = useLocation();
  return (
    <header className="sticky top-0 z-20 border-b border-edge bg-base/95 backdrop-blur">
      <div className="mx-auto flex h-14 max-w-[1600px] items-center gap-8 px-5">
        <Link to="/" className="group flex items-baseline gap-3">
          <span className="font-mono text-lg font-bold tracking-[0.25em] text-amber">
            SUNRISE
          </span>
          <span className="hidden text-xs text-ink-faint transition-colors group-hover:text-ink-dim md:inline">
            Wake up before the market does.
          </span>
        </Link>

        <nav className="flex items-center gap-1">
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              label={item.label}
              active={
                item.to === "/"
                  ? pathname === "/"
                  : pathname.startsWith(item.to)
              }
            />
          ))}
        </nav>

        <div className="ml-auto">
          <LiveDot connected={streamStatus === "connected"} />
        </div>
      </div>
    </header>
  );
}

function NavLink({
  to,
  label,
  active,
}: {
  to: string;
  label: string;
  active: boolean;
}) {
  return (
    <Link
      to={to}
      className={`rounded px-3 py-1.5 text-sm transition-colors ${
        active
          ? "bg-surface-2 text-amber"
          : "text-ink-dim hover:bg-surface hover:text-ink"
      }`}
    >
      {label}
    </Link>
  );
}
