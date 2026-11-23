import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { useAuth } from "../services/auth";
import { useNow } from "../hooks/usePolling";
import { cn } from "../lib/cn";
import { LiveDot } from "./StatusDot";
import {
  ArrowUpRight,
  Command,
  Menu,
  Search,
  SunriseMark,
  X,
} from "./icons";

const NAV = [
  { to: "/", label: "Pulse", hint: "Market pulse" },
  { to: "/scrapers", label: "Collectors", hint: "Collector health" },
  { to: "/system", label: "Operations", hint: "System" },
];

function MarketClock() {
  const now = useNow(1_000);
  const time = new Intl.DateTimeFormat("en-IN", {
    timeZone: "Asia/Kolkata",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  }).format(new Date(now));
  return (
    <div className="hidden items-center gap-2 xl:flex">
      <span className="h-1 w-1 rounded-full bg-amber/60" />
      <span className="font-mono text-[10px] uppercase tracking-[0.16em] text-ink-faint">
        IST <span className="text-ink-dim">{time}</span>
      </span>
    </div>
  );
}

export function Header({
  streamStatus,
  onOpenCommand,
}: {
  streamStatus: "connecting" | "connected" | "error";
  onOpenCommand: () => void;
}) {
  const { pathname } = useLocation();
  const { user, ready, configured, signIn, signOut } = useAuth();
  const [menuOpen, setMenuOpen] = useState(false);

  useEffect(() => {
    setMenuOpen(false);
  }, [pathname]);

  return (
    <header className="sticky top-0 z-40 border-b border-edge/80 bg-base/85 backdrop-blur-xl">
      <div className="mx-auto flex h-16 max-w-[1600px] items-center gap-6 px-5">
        <Link to="/" className="group flex shrink-0 items-center gap-3">
          <span className="flex h-9 w-9 items-center justify-center rounded-xl border border-amber/25 bg-amber/[0.08] text-amber transition-colors group-hover:border-amber/50">
            <SunriseMark className="h-5 w-5" />
          </span>
          <span className="leading-none">
            <span className="block font-mono text-sm font-bold tracking-[0.26em] text-ink">
              SUNRISE
            </span>
            <span className="mt-1 hidden text-[10px] tracking-wide text-ink-faint sm:block">
              Market intelligence
            </span>
          </span>
        </Link>

        <nav className="hidden items-center gap-1 md:flex" aria-label="Primary">
          {NAV.map((item) => {
            const active = item.to === "/" ? pathname === "/" : pathname.startsWith(item.to);
            return (
              <Link
                key={item.to}
                to={item.to}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "relative rounded-lg px-3 py-2 text-sm transition-colors",
                  active
                    ? "text-ink"
                    : "text-ink-dim hover:bg-white/[0.04] hover:text-ink",
                )}
              >
                {item.label}
                {active && (
                  <span className="absolute inset-x-3 -bottom-[13px] h-px bg-amber" />
                )}
              </Link>
            );
          })}
        </nav>

        <div className="ml-auto flex items-center gap-2.5">
          <MarketClock />
          <LiveDot connected={streamStatus === "connected"} />
          <button
            type="button"
            onClick={onOpenCommand}
            className="hidden h-9 cursor-pointer items-center gap-2 rounded-lg border border-edge bg-surface-2/50 px-3 text-xs text-ink-faint transition-colors hover:border-edge-bright hover:text-ink sm:flex"
          >
            <Search className="h-3.5 w-3.5" />
            Search
            <span className="ml-1 flex items-center gap-1 rounded border border-edge bg-base px-1 py-0.5 font-mono text-[9px] text-ink-faint">
              <Command className="h-2.5 w-2.5" />K
            </span>
          </button>
          {configured && ready && (
            <div className="hidden sm:block">
              {user ? (
                <button
                  type="button"
                  onClick={() => void signOut()}
                  title="Sign out"
                  className="flex max-w-[190px] cursor-pointer items-center gap-2 rounded-lg border border-edge bg-surface-2/50 px-2.5 py-1.5 text-xs text-ink-dim transition-colors hover:border-edge-bright hover:text-ink"
                >
                  <span className="flex h-5 w-5 items-center justify-center rounded-full bg-amber/15 font-mono text-[9px] font-semibold text-amber">
                    {String(user.profile.email || "S").slice(0, 1).toUpperCase()}
                  </span>
                  <span className="truncate">{String(user.profile.email || "Account")}</span>
                </button>
              ) : (
                <button
                  type="button"
                  onClick={() => void signIn()}
                  className="cursor-pointer rounded-lg border border-amber/30 bg-amber/[0.08] px-3 py-1.5 text-xs font-medium text-amber transition-colors hover:border-amber/60 hover:bg-amber/15"
                >
                  Sign in
                </button>
              )}
            </div>
          )}
          <button
            type="button"
            aria-label={menuOpen ? "Close menu" : "Open menu"}
            aria-expanded={menuOpen}
            onClick={() => setMenuOpen((open) => !open)}
            className="flex h-9 w-9 cursor-pointer items-center justify-center rounded-lg border border-edge bg-surface-2/50 text-ink-dim md:hidden"
          >
            {menuOpen ? <X className="h-4 w-4" /> : <Menu className="h-4 w-4" />}
          </button>
        </div>
      </div>

      {menuOpen && (
        <div className="border-t border-edge bg-base/95 px-5 py-4 md:hidden">
          <nav className="flex flex-col" aria-label="Mobile">
            {NAV.map((item) => {
              const active = item.to === "/" ? pathname === "/" : pathname.startsWith(item.to);
              return (
                <Link
                  key={item.to}
                  to={item.to}
                  className={cn(
                    "flex items-center justify-between rounded-lg px-3 py-3 text-sm",
                    active ? "bg-surface-2 text-ink" : "text-ink-dim",
                  )}
                >
                  {item.hint}
                  <ArrowUpRight className="h-4 w-4 text-ink-faint" />
                </Link>
              );
            })}
          </nav>
          <div className="mt-4 flex items-center gap-2">
            <button
              type="button"
              onClick={onOpenCommand}
              className="flex h-10 flex-1 items-center gap-2 rounded-lg border border-edge bg-surface-2/60 px-3 text-sm text-ink-dim"
            >
              <Search className="h-4 w-4" />
              Search the wire
            </button>
            {configured && ready && !user && (
              <button
                type="button"
                onClick={() => void signIn()}
                className="h-10 rounded-lg border border-amber/30 bg-amber/10 px-3 text-xs font-medium text-amber"
              >
                Sign in
              </button>
            )}
            {configured && ready && user && (
              <button
                type="button"
                onClick={() => void signOut()}
                className="h-10 rounded-lg border border-edge bg-surface-2/60 px-3 text-xs text-ink-dim"
              >
                Sign out
              </button>
            )}
          </div>
        </div>
      )}
    </header>
  );
}
