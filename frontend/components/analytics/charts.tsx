"use client";

import React from "react";

/**
 * Minimal, dependency-free chart primitives for the analytics dashboard.
 * No charting library is installed in this project (package.json has none)
 * and the dashboard's volume doesn't justify adding one -- these render
 * plain CSS/SVG from already-fetched data, nothing fabricated or sampled.
 */

export function StatCard({
  label,
  value,
  hint,
  tooltip,
}: {
  label: string;
  value: string;
  hint?: string;
  tooltip?: string;
}) {
  return (
    <div className="bg-white border border-[#E5E5DE] rounded-xl p-4 flex flex-col gap-1" title={tooltip}>
      <span className="text-xs font-medium text-[#737C76] uppercase tracking-wide">{label}</span>
      <span className="text-2xl font-heading font-bold text-[#202B28] tabular-nums">{value}</span>
      {hint && <span className="text-xs text-[#9AA39D]">{hint}</span>}
    </div>
  );
}

export function Panel({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="bg-white border border-[#E5E5DE] rounded-xl p-4 flex flex-col gap-3">
      <div>
        <h3 className="text-sm font-semibold text-[#202B28]">{title}</h3>
        {subtitle && <p className="text-xs text-[#9AA39D]">{subtitle}</p>}
      </div>
      {children}
    </div>
  );
}

export function EmptyState({ message }: { message: string }) {
  return <p className="text-sm text-[#9AA39D] py-6 text-center">{message}</p>;
}

export interface BarDatum {
  label: string;
  value: number;
  secondary?: string;
}

export function HorizontalBarList({ data, color = "#315C50" }: { data: BarDatum[]; color?: string }) {
  if (data.length === 0) return <EmptyState message="No data for this range." />;
  const max = Math.max(...data.map((d) => d.value), 1);
  return (
    <div className="flex flex-col gap-2.5">
      {data.map((d) => (
        <div key={d.label} className="flex items-center gap-3">
          <span className="w-32 shrink-0 text-xs text-[#737C76] truncate" title={d.label}>
            {d.label}
          </span>
          <div className="flex-1 h-5 bg-[#F0F1EC] rounded-md overflow-hidden">
            <div
              className="h-full rounded-md transition-all"
              style={{ width: `${(d.value / max) * 100}%`, backgroundColor: color }}
            />
          </div>
          <span className="w-16 shrink-0 text-xs font-semibold text-[#202B28] tabular-nums text-right">
            {d.secondary ?? d.value}
          </span>
        </div>
      ))}
    </div>
  );
}

export function TrendBars({ data, color = "#173B35" }: { data: { date: string; count: number }[]; color?: string }) {
  if (data.length === 0) return <EmptyState message="No activity in this range." />;
  const max = Math.max(...data.map((d) => d.count), 1);
  return (
    <div className="flex items-end gap-1 h-32">
      {data.map((d) => (
        <div key={d.date} className="flex-1 flex flex-col items-center gap-1 group relative">
          <div className="w-full flex items-end h-24">
            <div
              className="w-full rounded-t-sm transition-all"
              style={{ height: `${(d.count / max) * 100}%`, backgroundColor: color, minHeight: d.count > 0 ? 2 : 0 }}
              title={`${d.date}: ${d.count}`}
            />
          </div>
          <span className="text-[10px] text-[#9AA39D] rotate-0">{d.date.slice(5)}</span>
        </div>
      ))}
    </div>
  );
}

export interface FunnelDatum {
  stage: string;
  count: number;
  conversionPercent: number | null;
}

export function Funnel({ data }: { data: FunnelDatum[] }) {
  if (data.length === 0 || data[0].count === 0) return <EmptyState message="No leads in this range." />;
  const max = data[0].count || 1;
  return (
    <div className="flex flex-col gap-2">
      {data.map((stage) => (
        <div key={stage.stage} className="flex items-center gap-3">
          <span className="w-36 shrink-0 text-xs text-[#737C76] truncate">{stage.stage}</span>
          <div className="flex-1 h-6 bg-[#F0F1EC] rounded-md overflow-hidden">
            <div
              className="h-full rounded-md bg-[#C47A55] flex items-center justify-end pr-2"
              style={{ width: `${Math.max((stage.count / max) * 100, stage.count > 0 ? 4 : 0)}%` }}
            >
              <span className="text-xs font-semibold text-white">{stage.count}</span>
            </div>
          </div>
          <span className="w-14 shrink-0 text-xs text-[#9AA39D] text-right">
            {stage.conversionPercent !== null ? `${stage.conversionPercent}%` : "—"}
          </span>
        </div>
      ))}
    </div>
  );
}
