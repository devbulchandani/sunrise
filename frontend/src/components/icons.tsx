import type { ReactNode, SVGProps } from "react";

type IconProps = SVGProps<SVGSVGElement> & { strokeWidth?: number };

function Glyph({
  children,
  strokeWidth = 1.6,
  className = "h-4 w-4",
  ...props
}: IconProps & { children: ReactNode }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      className={className}
      {...props}
    >
      {children}
    </svg>
  );
}

export function SunriseMark({ className = "h-6 w-6", ...props }: IconProps) {
  return (
    <svg
      viewBox="0 0 32 32"
      fill="none"
      aria-hidden="true"
      className={className}
      {...props}
    >
      <path
        d="M4 23h24M8 19a8 8 0 0 1 16 0"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
      />
      <path
        d="M16 4v3.5M6.8 8.2l2.5 2.5M25.2 8.2l-2.5 2.5M4 27h24"
        stroke="currentColor"
        strokeWidth="1.4"
        strokeLinecap="round"
        opacity="0.55"
      />
    </svg>
  );
}

export const Pulse = (p: IconProps) => (
  <Glyph {...p}>
    <path d="M3 12h3.5l2-6 3.5 12 2.5-8 1.8 4H21" />
  </Glyph>
);

export const Radar = (p: IconProps) => (
  <Glyph {...p}>
    <circle cx="12" cy="12" r="8.5" />
    <circle cx="12" cy="12" r="4.5" />
    <path d="M12 12 18 6" />
    <circle cx="12" cy="12" r="1" fill="currentColor" stroke="none" />
  </Glyph>
);

export const Grid = (p: IconProps) => (
  <Glyph {...p}>
    <rect x="3.5" y="3.5" width="7" height="7" rx="1.5" />
    <rect x="13.5" y="3.5" width="7" height="7" rx="1.5" />
    <rect x="3.5" y="13.5" width="7" height="7" rx="1.5" />
    <rect x="13.5" y="13.5" width="7" height="7" rx="1.5" />
  </Glyph>
);

export const Terminal = (p: IconProps) => (
  <Glyph {...p}>
    <rect x="3" y="4.5" width="18" height="15" rx="2.5" />
    <path d="m7 9 3 3-3 3M12.5 15H17" />
  </Glyph>
);

export const Search = (p: IconProps) => (
  <Glyph {...p}>
    <circle cx="10.5" cy="10.5" r="6.5" />
    <path d="m15.5 15.5 4.5 4.5" />
  </Glyph>
);

export const ArrowUpRight = (p: IconProps) => (
  <Glyph {...p}>
    <path d="M7 17 17 7M8 7h9v9" />
  </Glyph>
);

export const ArrowRight = (p: IconProps) => (
  <Glyph {...p}>
    <path d="M4 12h16M14 6l6 6-6 6" />
  </Glyph>
);

export const ChevronDown = (p: IconProps) => (
  <Glyph {...p}>
    <path d="m6 9 6 6 6-6" />
  </Glyph>
);

export const ChevronRight = (p: IconProps) => (
  <Glyph {...p}>
    <path d="m9 6 6 6-6 6" />
  </Glyph>
);

export const Clock = (p: IconProps) => (
  <Glyph {...p}>
    <circle cx="12" cy="12" r="8.5" />
    <path d="M12 7.5V12l3 2" />
  </Glyph>
);

export const Database = (p: IconProps) => (
  <Glyph {...p}>
    <ellipse cx="12" cy="6" rx="7.5" ry="3" />
    <path d="M4.5 6v6c0 1.66 3.36 3 7.5 3s7.5-1.34 7.5-3V6" />
    <path d="M4.5 12v6c0 1.66 3.36 3 7.5 3s7.5-1.34 7.5-3v-6" />
  </Glyph>
);

export const Server = (p: IconProps) => (
  <Glyph {...p}>
    <rect x="3.5" y="4" width="17" height="6" rx="1.5" />
    <rect x="3.5" y="14" width="17" height="6" rx="1.5" />
    <path d="M7 7h.01M7 17h.01M11 7h5M11 17h5" />
  </Glyph>
);

export const Zap = (p: IconProps) => (
  <Glyph {...p}>
    <path d="M13 2 4.5 13.5H11l-1 8.5L19.5 10H13l0-8Z" />
  </Glyph>
);

export const AlertTriangle = (p: IconProps) => (
  <Glyph {...p}>
    <path d="M10.3 3.9 2.8 17a2 2 0 0 0 1.7 3h15a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z" />
    <path d="M12 9v4M12 16.5h.01" />
  </Glyph>
);

export const Check = (p: IconProps) => (
  <Glyph {...p}>
    <path d="m4.5 12.5 5 5 10-11" />
  </Glyph>
);

export const X = (p: IconProps) => (
  <Glyph {...p}>
    <path d="m6 6 12 12M18 6 6 18" />
  </Glyph>
);

export const Menu = (p: IconProps) => (
  <Glyph {...p}>
    <path d="M4 7h16M4 12h16M4 17h16" />
  </Glyph>
);

export const Command = (p: IconProps) => (
  <Glyph {...p}>
    <path d="M9 6a3 3 0 1 0-3 3h12a3 3 0 1 0-3-3v12a3 3 0 1 0 3-3H6a3 3 0 1 0 3 3V6Z" />
  </Glyph>
);

export const Globe = (p: IconProps) => (
  <Glyph {...p}>
    <circle cx="12" cy="12" r="8.5" />
    <path d="M3.5 12h17M12 3.5c2.2 2.3 3.3 5.2 3.3 8.5S14.2 18.2 12 20.5C9.8 18.2 8.7 15.3 8.7 12S9.8 5.8 12 3.5Z" />
  </Glyph>
);

export const Gauge = (p: IconProps) => (
  <Glyph {...p}>
    <path d="M4 17a8 8 0 1 1 16 0" />
    <path d="m12 13 4-4" />
    <circle cx="12" cy="13" r="1.4" fill="currentColor" stroke="none" />
  </Glyph>
);

export const Bell = (p: IconProps) => (
  <Glyph {...p}>
    <path d="M18 9a6 6 0 1 0-12 0c0 5-2 6-2 6h16s-2-1-2-6" />
    <path d="M10 20a2.2 2.2 0 0 0 4 0" />
  </Glyph>
);

export const Refresh = (p: IconProps) => (
  <Glyph {...p}>
    <path d="M20 11a8 8 0 1 0-2.3 5.7" />
    <path d="M20 4v7h-7" />
  </Glyph>
);

export const External = (p: IconProps) => (
  <Glyph {...p}>
    <path d="M14 4h6v6M20 4 11 13" />
    <path d="M19 14v5a1.5 1.5 0 0 1-1.5 1.5h-12A1.5 1.5 0 0 1 4 19V7a1.5 1.5 0 0 1 1.5-1.5H10" />
  </Glyph>
);

export const Sparkle = (p: IconProps) => (
  <Glyph {...p}>
    <path d="M12 3v4M12 17v4M3 12h4M17 12h4M5.6 5.6l2.8 2.8M15.6 15.6l2.8 2.8M18.4 5.6l-2.8 2.8M8.4 15.6l-2.8 2.8" />
  </Glyph>
);

export const Filter = (p: IconProps) => (
  <Glyph {...p}>
    <path d="M4 5h16l-6.2 7.2V19l-3.6 2v-8.8L4 5Z" />
  </Glyph>
);

export const Layers = (p: IconProps) => (
  <Glyph {...p}>
    <path d="m12 3 8.5 4.5L12 12 3.5 7.5 12 3Z" />
    <path d="m3.5 12.5 8.5 4.5 8.5-4.5M3.5 17l8.5 4.5 8.5-4.5" />
  </Glyph>
);

export const Shield = (p: IconProps) => (
  <Glyph {...p}>
    <path d="M12 3 5 6v5.5c0 4.3 2.9 7.7 7 9.5 4.1-1.8 7-5.2 7-9.5V6l-7-3Z" />
    <path d="m9 12 2 2 4-4" />
  </Glyph>
);

export const Signal = (p: IconProps) => (
  <Glyph {...p}>
    <path d="M5 18v-3M9.7 18v-6M14.3 18V8M19 18V5" />
  </Glyph>
);

export const Wallet = (p: IconProps) => (
  <Glyph {...p}>
    <path d="M4 7.5A2.5 2.5 0 0 1 6.5 5H19a1 1 0 0 1 1 1v13a1 1 0 0 1-1 1H6.5A2.5 2.5 0 0 1 4 17.5v-10Z" />
    <path d="M4 8h15M15.5 13.5h2" />
    <circle cx="16.5" cy="13.5" r=".6" fill="currentColor" stroke="none" />
  </Glyph>
);

export const TrendingUp = (p: IconProps) => (
  <Glyph {...p}>
    <path d="m4 15 5-5 4 4 7-8" />
    <path d="M15 6h5v5" />
  </Glyph>
);

export const TrendingDown = (p: IconProps) => (
  <Glyph {...p}>
    <path d="m4 9 5 5 4-4 7 8" />
    <path d="M15 18h5v-5" />
  </Glyph>
);

export const Dot = ({ className = "h-1.5 w-1.5" }: { className?: string }) => (
  <span className={`inline-block rounded-full bg-current ${className}`} aria-hidden="true" />
);

export const LogOut = (p: IconProps) => (
  <Glyph {...p}>
    <path d="M14.5 4H18a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-3.5" />
    <path d="M10 8l-4 4 4 4M6 12h9" />
  </Glyph>
);

export const Send = (p: IconProps) => (
  <Glyph {...p}>
    <path d="M21 3 10.5 13.5" />
    <path d="m21 3-6.5 18-4-8-8-4L21 3Z" />
  </Glyph>
);
