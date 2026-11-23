import { useId } from "react";
import { cn } from "../lib/cn";

export type Tone = "amber" | "bull" | "bear" | "heal" | "info" | "ink";

export const TONE_HEX: Record<Tone, string> = {
  amber: "#F5A623",
  bull: "#42D9A0",
  bear: "#FF6B81",
  heal: "#5EEAD4",
  info: "#7DD3FC",
  ink: "#A6B2C2",
};

function normalize(data: number[]): number[] {
  if (data.length >= 2) return data;
  if (data.length === 1) return [data[0], data[0]];
  return [0, 0];
}

export function Sparkline({
  data,
  width = 140,
  height = 40,
  tone = "amber",
  fill = true,
  strokeWidth = 1.8,
  className,
}: {
  data: number[];
  width?: number;
  height?: number;
  tone?: Tone;
  fill?: boolean;
  strokeWidth?: number;
  className?: string;
}) {
  const gradientId = `spark-${useId().replace(/[^a-zA-Z0-9]/g, "")}`;
  const values = normalize(data);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const points = values.map((value, index) => {
    const x = (index / (values.length - 1)) * width;
    const y = height - 3 - ((value - min) / span) * (height - 8);
    return [x, y] as const;
  });
  const line = points
    .map(([x, y], index) => `${index === 0 ? "M" : "L"}${x.toFixed(1)} ${y.toFixed(1)}`)
    .join(" ");
  const area = `${line} L ${width} ${height} L 0 ${height} Z`;
  const color = TONE_HEX[tone];

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      className={cn("h-full w-full overflow-visible", className)}
      preserveAspectRatio="none"
      aria-hidden="true"
    >
      <defs>
        <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.32" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      {fill && <path d={area} fill={`url(#${gradientId})`} />}
      <path
        d={line}
        fill="none"
        stroke={color}
        strokeWidth={strokeWidth}
        strokeLinecap="round"
        strokeLinejoin="round"
        vectorEffect="non-scaling-stroke"
      />
      <circle
        cx={points[points.length - 1][0]}
        cy={points[points.length - 1][1]}
        r="2"
        fill={color}
      />
    </svg>
  );
}

export function Bars({
  data,
  max,
  tone = "amber",
  height = 30,
  className,
}: {
  data: number[];
  max?: number;
  tone?: Tone;
  height?: number;
  className?: string;
}) {
  const values = data.length ? data : [0];
  const ceiling = Math.max(max ?? 0, ...values, 1);
  const color = TONE_HEX[tone];
  return (
    <div
      className={cn("flex items-end gap-[3px]", className)}
      style={{ height }}
      aria-hidden="true"
    >
      {values.map((value, index) => (
        <span
          key={index}
          className="min-w-[2px] flex-1 rounded-[2px] transition-all duration-500"
          style={{
            height: `${Math.max((value / ceiling) * 100, 4)}%`,
            background: value === 0 ? "#1A2433" : color,
            opacity: value === 0 ? 1 : 0.35 + (value / ceiling) * 0.65,
          }}
        />
      ))}
    </div>
  );
}

export function RadialGauge({
  value,
  size = 168,
  stroke = 8,
  tone = "amber",
  children,
  label,
}: {
  value: number;
  size?: number;
  stroke?: number;
  tone?: Tone;
  children?: React.ReactNode;
  label?: string;
}) {
  const gradientId = `gauge-${useId().replace(/[^a-zA-Z0-9]/g, "")}`;
  const radius = (size - stroke) / 2;
  const circumference = 2 * Math.PI * radius;
  const clamped = Math.max(0, Math.min(100, value));
  const offset = circumference * (1 - clamped / 100);
  const color = TONE_HEX[tone];

  return (
    <div
      className="relative inline-flex items-center justify-center"
      style={{ width: size, height: size }}
      role="img"
      aria-label={label ?? `${Math.round(clamped)} out of 100`}
    >
      <svg width={size} height={size} className="-rotate-90" aria-hidden="true">
        <defs>
          <linearGradient id={gradientId} x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity="0.45" />
            <stop offset="100%" stopColor={color} />
          </linearGradient>
        </defs>
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="#1A2433"
          strokeWidth={stroke}
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={`url(#${gradientId})`}
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          style={{ transition: "stroke-dashoffset 900ms cubic-bezier(0.16,1,0.3,1)" }}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center text-center">
        {children}
      </div>
    </div>
  );
}
