import type { IntensityPoint } from "@/utils/analysis";
import { emotionLabel, formatSeconds } from "./format";

/**
 * 情绪强度曲线（纯 SVG，服务端渲染）。
 * 折线与峰值点使用 primary，网格与标签保持中性。
 */
export function EmotionCurve({
  curve,
  peakTimestamp,
}: {
  curve: IntensityPoint[];
  peakTimestamp?: number;
}) {
  const points = curve.filter(
    (p): p is IntensityPoint & { timestamp: number; intensity: number } =>
      typeof p.timestamp === "number" && typeof p.intensity === "number",
  );
  if (points.length === 0) return null;

  const width = 640;
  const height = 190;
  const padX = 32;
  const padTop = 24;
  const padBottom = 40;
  const innerW = width - padX * 2;
  const innerH = height - padTop - padBottom;

  const maxT = Math.max(...points.map((p) => p.timestamp), 1);
  const x = (t: number) => padX + (t / maxT) * innerW;
  const y = (v: number) => padTop + (1 - Math.min(10, Math.max(0, v)) / 10) * innerH;

  const polyline = points.map((p) => `${x(p.timestamp)},${y(p.intensity)}`).join(" ");
  const area = `${padX},${padTop + innerH} ${polyline} ${padX + innerW},${padTop + innerH}`;

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      className="h-auto w-full"
      role="img"
      aria-label="情绪强度曲线"
    >
      {/* 网格线 */}
      {[0, 5, 10].map((v) => (
        <g key={v}>
          <line
            x1={padX}
            x2={padX + innerW}
            y1={y(v)}
            y2={y(v)}
            stroke="var(--border)"
            strokeDasharray="3 4"
          />
          <text
            x={padX - 8}
            y={y(v) + 3}
            textAnchor="end"
            fontSize="10"
            fill="var(--muted-foreground)"
            className="font-numeric"
          >
            {v}
          </text>
        </g>
      ))}
      {/* 面积填充 */}
      <polygon points={area} fill="var(--primary)" opacity="0.08" />
      {/* 折线 */}
      <polyline
        points={polyline}
        fill="none"
        stroke="var(--primary)"
        strokeWidth="2"
        strokeLinejoin="round"
        strokeLinecap="round"
      />
      {/* 数据点 */}
      {points.map((p, i) => {
        const isPeak = peakTimestamp != null && p.timestamp === peakTimestamp;
        return (
          <g key={`${p.timestamp}-${i}`}>
            <circle
              cx={x(p.timestamp)}
              cy={y(p.intensity)}
              r={isPeak ? 5 : 3.5}
              fill={isPeak ? "var(--primary)" : "var(--background)"}
              stroke="var(--primary)"
              strokeWidth="2"
            />
            <text
              x={x(p.timestamp)}
              y={y(p.intensity) - 10}
              textAnchor="middle"
              fontSize="11"
              fontWeight="600"
              fill="var(--foreground)"
              className="font-numeric"
            >
              {p.intensity.toFixed(1)}
            </text>
            <text
              x={x(p.timestamp)}
              y={padTop + innerH + 16}
              textAnchor="middle"
              fontSize="10"
              fill="var(--muted-foreground)"
            >
              {emotionLabel(p.emotion ?? undefined)}
            </text>
            <text
              x={x(p.timestamp)}
              y={padTop + innerH + 30}
              textAnchor="middle"
              fontSize="10"
              fill="var(--muted-foreground)"
              className="font-numeric"
            >
              {formatSeconds(p.timestamp)}
            </text>
          </g>
        );
      })}
    </svg>
  );
}
