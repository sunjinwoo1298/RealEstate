"use client";

import React, { useEffect, useMemo, useState } from "react";
import { RefreshCw } from "lucide-react";
import { useAuth } from "@/lib/auth-context";
import {
  apiClient,
  ApiError,
  AnalyticsFilterParams,
  DateRangePreset,
  ExecutiveAnalytics,
  FunnelAnalytics,
  LeadAnalytics,
  OverviewAnalytics,
  ProjectPublic,
  QualificationAnalytics,
  ReminderAnalytics,
  ResponseTimeAnalytics,
  SiteVisitAnalytics,
  SourceAnalytics,
} from "@/lib/api-client";
import {
  BarDatum,
  EmptyState,
  Funnel,
  HorizontalBarList,
  Panel,
  StatCard,
  TrendBars,
} from "@/components/analytics/charts";

const RANGE_OPTIONS: { value: DateRangePreset; label: string }[] = [
  { value: "TODAY", label: "Today" },
  { value: "LAST_7_DAYS", label: "Last 7 days" },
  { value: "LAST_30_DAYS", label: "Last 30 days" },
  { value: "THIS_MONTH", label: "This month" },
  { value: "PREVIOUS_MONTH", label: "Previous month" },
  { value: "CUSTOM", label: "Custom range" },
];

function formatSeconds(seconds: number | null): string {
  if (seconds === null) return "—";
  if (seconds < 60) return `${Math.round(seconds)}s`;
  if (seconds < 3600) return `${Math.round(seconds / 60)}m`;
  if (seconds < 86400) return `${(seconds / 3600).toFixed(1)}h`;
  return `${(seconds / 86400).toFixed(1)}d`;
}

function formatPercent(value: number | null): string {
  return value === null ? "—" : `${value}%`;
}

interface Data {
  overview: OverviewAnalytics;
  leads: LeadAnalytics;
  sources: SourceAnalytics;
  responseTimes: ResponseTimeAnalytics;
  qualification: QualificationAnalytics;
  funnel: FunnelAnalytics;
  siteVisits: SiteVisitAnalytics;
  executives: ExecutiveAnalytics;
  reminders: ReminderAnalytics;
}

export default function AnalyticsPage() {
  const { user } = useAuth();
  const canFilterByExecutive = user?.role === "ADMIN" || user?.role === "MANAGER";

  const [range, setRange] = useState<DateRangePreset>("LAST_30_DAYS");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [projectId, setProjectId] = useState("");
  const [executiveId, setExecutiveId] = useState("");
  const [projects, setProjects] = useState<ProjectPublic[]>([]);
  const [executiveOptions, setExecutiveOptions] = useState<{ id: string; name: string }[]>([]);

  const [data, setData] = useState<Data | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const filters: AnalyticsFilterParams = useMemo(
    () => ({
      range,
      date_from: range === "CUSTOM" ? dateFrom || undefined : undefined,
      date_to: range === "CUSTOM" ? dateTo || undefined : undefined,
      project_id: projectId || undefined,
      executive_id: executiveId || undefined,
    }),
    [range, dateFrom, dateTo, projectId, executiveId]
  );

  useEffect(() => {
    apiClient
      .listProjects({ is_active: true, limit: 100 })
      .then((res) => setProjects(res.items))
      .catch(() => undefined);
  }, []);

  const load = async () => {
    if (range === "CUSTOM" && (!dateFrom || !dateTo)) {
      setLoading(false);
      return;
    }
    setLoading(true);
    try {
      const [overview, leads, sources, responseTimes, qualification, funnel, siteVisits, executives, reminders] =
        await Promise.all([
          apiClient.getOverviewAnalytics(filters),
          apiClient.getLeadAnalytics(filters),
          apiClient.getSourceAnalytics(filters),
          apiClient.getResponseTimeAnalytics(filters),
          apiClient.getQualificationAnalytics(filters),
          apiClient.getFunnelAnalytics(filters),
          apiClient.getSiteVisitAnalytics(filters),
          apiClient.getExecutiveAnalytics(filters),
          apiClient.getReminderAnalytics(filters),
        ]);
      setData({ overview, leads, sources, responseTimes, qualification, funnel, siteVisits, executives, reminders });
      if (canFilterByExecutive) {
        setExecutiveOptions(executives.executives.map((e) => ({ id: e.executive_id, name: e.executive_name })));
      }
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load analytics.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- intentional data fetch on filter change
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filters]);

  const dateRangeLabel = data
    ? `${new Date(data.overview.date_range.start_utc).toLocaleDateString("en-IN", { timeZone: "Asia/Kolkata" })} – ${new Date(
        data.overview.date_range.end_utc
      ).toLocaleDateString("en-IN", { timeZone: "Asia/Kolkata" })}`
    : "";

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-start justify-between flex-wrap gap-4">
        <div>
          <h1 className="text-[26px] font-heading font-bold text-[#202B28]">Analytics</h1>
          <p className="text-sm text-[#737C76] mt-1">
            Lead acquisition, AI engagement, visits and conversion
            {dateRangeLabel && <span className="text-[#9AA39D]"> • {dateRangeLabel} (IST)</span>}
          </p>
        </div>
        <button
          onClick={load}
          className="flex items-center gap-2 px-3 py-2 text-sm font-medium rounded-lg border border-[#E5E5DE] bg-white hover:bg-[#F0F1EC] text-[#202B28] transition-colors"
        >
          <RefreshCw className="w-4 h-4" /> Refresh
        </button>
      </div>

      {/* Filters */}
      <div className="bg-white border border-[#E5E5DE] rounded-xl p-4 flex flex-wrap items-end gap-4">
        <div className="flex flex-col gap-1">
          <label className="text-xs font-medium text-[#737C76]">Date range</label>
          <select
            value={range}
            onChange={(e) => setRange(e.target.value as DateRangePreset)}
            className="h-10 px-3 rounded-lg border border-[#E5E5DE] bg-white text-sm text-[#202B28] min-w-[160px]"
          >
            {RANGE_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </div>
        {range === "CUSTOM" && (
          <>
            <div className="flex flex-col gap-1">
              <label className="text-xs font-medium text-[#737C76]">From</label>
              <input
                type="date"
                value={dateFrom}
                onChange={(e) => setDateFrom(e.target.value)}
                className="h-10 px-3 rounded-lg border border-[#E5E5DE] bg-white text-sm text-[#202B28]"
              />
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-xs font-medium text-[#737C76]">To</label>
              <input
                type="date"
                value={dateTo}
                onChange={(e) => setDateTo(e.target.value)}
                className="h-10 px-3 rounded-lg border border-[#E5E5DE] bg-white text-sm text-[#202B28]"
              />
            </div>
          </>
        )}
        <div className="flex flex-col gap-1">
          <label className="text-xs font-medium text-[#737C76]">Project</label>
          <select
            value={projectId}
            onChange={(e) => setProjectId(e.target.value)}
            className="h-10 px-3 rounded-lg border border-[#E5E5DE] bg-white text-sm text-[#202B28] min-w-[160px]"
          >
            <option value="">All projects</option>
            {projects.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        </div>
        {canFilterByExecutive && (
          <div className="flex flex-col gap-1">
            <label className="text-xs font-medium text-[#737C76]">Sales executive</label>
            <select
              value={executiveId}
              onChange={(e) => setExecutiveId(e.target.value)}
              className="h-10 px-3 rounded-lg border border-[#E5E5DE] bg-white text-sm text-[#202B28] min-w-[160px]"
            >
              <option value="">All executives</option>
              {executiveOptions.map((e) => (
                <option key={e.id} value={e.id}>
                  {e.name}
                </option>
              ))}
            </select>
          </div>
        )}
      </div>

      {error && (
        <div className="bg-[#FDF2F2] border border-[#F3D5D5] text-[#C34D4D] text-sm rounded-lg p-3">{error}</div>
      )}

      {range === "CUSTOM" && (!dateFrom || !dateTo) && (
        <div className="bg-[#FDF6EC] border border-[#F3E3C7] text-[#B7791F] text-sm rounded-lg p-3">
          Select both a start and end date for a custom range.
        </div>
      )}

      {loading && !data && <p className="text-sm text-[#737C76] py-10 text-center">Loading analytics…</p>}

      {data && (
        <>
          {/* Overview */}
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
            <StatCard label="Unique Leads" value={String(data.overview.total_unique_leads)} />
            <StatCard label="Enquiries Received" value={String(data.overview.total_enquiry_records)} />
            <StatCard
              label="Median Response"
              value={formatSeconds(data.overview.median_response_time_seconds)}
              tooltip="Median time from lead creation to the first AI/staff reply"
            />
            <StatCard
              label="Qualification Rate"
              value={formatPercent(data.overview.qualification_rate_percent)}
              tooltip="Share of this period's leads that are currently fully qualified"
            />
            <StatCard label="Visits Booked" value={String(data.overview.site_visits_booked)} />
            <StatCard
              label="Attendance Rate"
              value={formatPercent(data.overview.attendance_rate_percent)}
              tooltip="Completed / (Completed + No-show), cancelled visits excluded"
            />
          </div>

          {/* Charts */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <Panel title="Lead Acquisition Trend" subtitle="Unique leads created per day (IST)">
              <TrendBars data={data.leads.trend.map((t) => ({ date: t.date, count: t.unique_leads }))} />
            </Panel>
            <Panel title="Leads by Source" subtitle="Unique leads attributed to each channel">
              <HorizontalBarList
                data={data.leads.by_source.map(
                  (s): BarDatum => ({
                    label: s.source_type,
                    value: s.unique_lead_count,
                    secondary: `${s.unique_lead_count} (${s.percent_of_total_unique_leads ?? 0}%)`,
                  })
                )}
              />
            </Panel>
            <Panel title="Leads by Project" subtitle="Via each buyer's current qualification">
              <HorizontalBarList
                data={data.leads.by_project.map((p): BarDatum => ({
                  label: p.project_name ?? "Unspecified",
                  value: p.unique_lead_count,
                }))}
                color="#C47A55"
              />
            </Panel>
            <Panel
              title="Response Time Distribution"
              subtitle={`${data.responseTimes.leads_with_response} responded, ${data.responseTimes.leads_without_response} awaiting a first response`}
            >
              <HorizontalBarList
                data={data.responseTimes.distribution_buckets.map((b): BarDatum => ({ label: b.label, value: b.count }))}
                color="#4779A8"
              />
            </Panel>
            <Panel title="Sales Funnel" subtitle={data.funnel.note}>
              <Funnel
                data={data.funnel.stages.map((s) => ({
                  stage: s.stage,
                  count: s.count,
                  conversionPercent: s.conversion_from_previous_percent,
                }))}
              />
            </Panel>
            <Panel
              title="Site Visits & Attendance"
              subtitle={`Booking activity • Attendance ${formatPercent(
                data.siteVisits.attendance_rate_percent
              )} • No-show ${formatPercent(data.siteVisits.no_show_rate_percent)}`}
            >
              <TrendBars data={data.siteVisits.trend} color="#315C50" />
            </Panel>
            <Panel title="Executive Performance" subtitle="Site visits booked per executive, this period">
              <HorizontalBarList
                data={data.executives.executives.map((e): BarDatum => ({
                  label: e.executive_name,
                  value: e.site_visits_booked,
                }))}
                color="#173B35"
              />
            </Panel>
            <Panel title="Reminder Execution Status" subtitle={`Failure rate ${formatPercent(data.reminders.failure_rate_percent)}`}>
              <HorizontalBarList
                data={data.reminders.status_breakdown
                  .filter((s) => s.count > 0)
                  .map((s): BarDatum => ({ label: s.status, value: s.count }))}
                color="#B7791F"
              />
            </Panel>
          </div>

          {/* Tables */}
          <Panel title="Source Performance Breakdown">
            {data.sources.sources.length === 0 ? (
              <EmptyState message="No enquiries in this range." />
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-[#E5E5DE] text-left text-xs text-[#737C76] uppercase">
                      <th className="py-2 pr-4">Source</th>
                      <th className="py-2 pr-4">Enquiries</th>
                      <th className="py-2 pr-4">Unique Leads</th>
                      <th className="py-2 pr-4">% of Total</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.sources.sources.map((s) => (
                      <tr key={s.source_type} className="border-b border-[#F0F1EC]">
                        <td className="py-2 pr-4 text-[#202B28] font-medium">{s.source_type}</td>
                        <td className="py-2 pr-4 tabular-nums">{s.enquiry_count}</td>
                        <td className="py-2 pr-4 tabular-nums">{s.unique_lead_count}</td>
                        <td className="py-2 pr-4 tabular-nums">{formatPercent(s.percent_of_total_unique_leads)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Panel>

          <Panel title="Project Performance Breakdown">
            {data.leads.by_project.length === 0 ? (
              <EmptyState message="No qualified project interest in this range." />
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-[#E5E5DE] text-left text-xs text-[#737C76] uppercase">
                      <th className="py-2 pr-4">Project</th>
                      <th className="py-2 pr-4">Unique Leads</th>
                      <th className="py-2 pr-4">Visits Booked</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.leads.by_project.map((p) => {
                      const visitRow = data.siteVisits.by_project.find((v) => v.project_id === p.project_id);
                      return (
                        <tr key={p.project_id ?? "unspecified"} className="border-b border-[#F0F1EC]">
                          <td className="py-2 pr-4 text-[#202B28] font-medium">{p.project_name ?? "Unspecified"}</td>
                          <td className="py-2 pr-4 tabular-nums">{p.unique_lead_count}</td>
                          <td className="py-2 pr-4 tabular-nums">{visitRow?.count ?? 0}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </Panel>

          <Panel title="Sales Executive Performance">
            {data.executives.executives.length === 0 ? (
              <EmptyState message="No sales executives found." />
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-[#E5E5DE] text-left text-xs text-[#737C76] uppercase">
                      <th className="py-2 pr-4">Executive</th>
                      <th className="py-2 pr-4">Assigned Leads</th>
                      <th className="py-2 pr-4">Contacted</th>
                      <th className="py-2 pr-4">Qualified</th>
                      <th className="py-2 pr-4">Accepted Handoffs</th>
                      <th className="py-2 pr-4">Visits Booked</th>
                      <th className="py-2 pr-4">Visits Completed</th>
                      <th className="py-2 pr-4">No-shows</th>
                      <th className="py-2 pr-4">Attendance Rate</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.executives.executives.map((e) => (
                      <tr key={e.executive_id} className="border-b border-[#F0F1EC]">
                        <td className="py-2 pr-4 text-[#202B28] font-medium">{e.executive_name}</td>
                        <td className="py-2 pr-4 tabular-nums">{e.assigned_leads_current}</td>
                        <td className="py-2 pr-4 tabular-nums">{e.leads_contacted}</td>
                        <td className="py-2 pr-4 tabular-nums">{e.qualified_leads}</td>
                        <td className="py-2 pr-4 tabular-nums">{e.accepted_handoffs}</td>
                        <td className="py-2 pr-4 tabular-nums">{e.site_visits_booked}</td>
                        <td className="py-2 pr-4 tabular-nums">{e.site_visits_completed}</td>
                        <td className="py-2 pr-4 tabular-nums">{e.no_show_count}</td>
                        <td className="py-2 pr-4 tabular-nums">{formatPercent(e.attendance_rate_percent)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Panel>
        </>
      )}
    </div>
  );
}
