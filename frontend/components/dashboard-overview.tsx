"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { apiClient, OverviewAnalytics, ResponseTimeAnalytics } from "@/lib/api-client";
import { useAuth } from "@/lib/auth-context";
import { AlarmClock, ArrowRight, CalendarCheck, Clock, Flag, UserCheck, Users } from "lucide-react";

function formatDuration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) return "—";
  if (seconds < 90) return `${Math.round(seconds)} sec`;
  if (seconds < 5400) return `${Math.round(seconds / 60)} min`;
  return `${(seconds / 3600).toFixed(1)} hr`;
}

const formatPercent = (v: number | null | undefined) => (v === null || v === undefined ? "—" : `${v}%`);

export function DashboardOverview() {
  const { user } = useAuth();
  const [overview, setOverview] = useState<OverviewAnalytics | null>(null);
  const [response, setResponse] = useState<ResponseTimeAnalytics | null>(null);
  const [failed, setFailed] = useState(false);
  const [flaggedToday, setFlaggedToday] = useState<number | null>(null);
  const canReview = user?.role === "ADMIN" || user?.role === "MANAGER";

  useEffect(() => {
    apiClient.getOverviewAnalytics({ range: "LAST_30_DAYS" }).then(setOverview).catch(() => setFailed(true));
    apiClient.getResponseTimeAnalytics({ range: "LAST_30_DAYS" }).then(setResponse).catch(() => undefined);
  }, []);

  useEffect(() => {
    if (!canReview) return;
    apiClient
      .listConversations({ flagged: true, limit: 1 })
      .then((r) => setFlaggedToday(r.total))
      .catch(() => undefined);
  }, [canReview]);

  const visitRate =
    overview && overview.total_unique_leads > 0
      ? `${((overview.site_visits_booked / overview.total_unique_leads) * 100).toFixed(1)}%`
      : "—";

  const cards = [
    {
      label: "New enquiries",
      value: overview ? String(overview.total_unique_leads) : "—",
      hint: "Unique buyers, last 30 days",
      icon: Users,
    },
    {
      label: "Median first response",
      value: formatDuration(overview?.median_response_time_seconds),
      hint: "Enquiry to first reply",
      icon: Clock,
    },
    {
      label: "Answered within 2 minutes",
      value: formatPercent(response?.responded_within_2_minutes_percent),
      hint: "Share of enquiries replied to quickly",
      icon: Clock,
    },
    {
      label: "Not reached in 48 hours",
      value: response ? String(response.leads_not_responded_within_48h) : "—",
      hint: "Enquiries still waiting for a reply",
      icon: AlarmClock,
    },
    {
      label: "Site visits booked",
      value: overview ? String(overview.site_visits_booked) : "—",
      hint: `${visitRate} of enquiries`,
      icon: CalendarCheck,
    },
    {
      label: "Show-up rate",
      value: formatPercent(overview?.attendance_rate_percent),
      hint: "Of visits already due",
      icon: UserCheck,
    },
  ];

  return (
    <div className="space-y-8">
      <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold font-heading text-[#202B28] tracking-tight">
            Welcome{user?.full_name ? `, ${user.full_name.split(" ")[0]}` : ""}
          </h1>
          <p className="text-sm text-[#737C76] mt-1">Here is how enquiries and site visits are doing over the last 30 days.</p>
        </div>
        <Link href="/analytics" className="inline-flex items-center gap-1.5 text-sm font-semibold text-[#173B35] hover:text-[#315C50]">
          Full analytics <ArrowRight className="w-4 h-4" />
        </Link>
      </div>

      {failed && (
        <p className="text-sm text-[#C34D4D] bg-[#FDF2F2] border border-[#F8D2D2] rounded-lg px-4 py-3">
          These figures could not be loaded right now. Please refresh in a moment.
        </p>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {cards.map(({ label, value, hint, icon: Icon }) => (
          <div key={label} className="bg-white p-5 rounded-xl border border-[#E5E5DE] shadow-xs">
            <div className="flex items-center justify-between">
              <span className="text-[11px] font-semibold text-[#737C76] uppercase tracking-wider">{label}</span>
              <Icon className="w-4 h-4 text-[#C47A55]" />
            </div>
            <p className="mt-3 text-3xl font-bold font-heading text-[#202B28]">{value}</p>
            <p className="text-xs text-[#737C76] mt-1">{hint}</p>
          </div>
        ))}
      </div>

      {canReview && (
        <Link
          href="/conversations?flagged=1"
          className="flex items-center justify-between bg-white p-5 rounded-xl border border-[#E5E5DE] hover:border-[#C5C5BB] transition-colors"
        >
          <span className="flex items-center gap-3">
            <Flag className="w-5 h-5 text-[#C47A55]" />
            <span>
              <span className="block font-heading font-semibold text-[#202B28]">
                {flaggedToday === null ? "Chats flagged today" : `${flaggedToday} chat${flaggedToday === 1 ? "" : "s"} flagged today`}
              </span>
              <span className="block text-sm text-[#737C76]">Price asks, complaints, requests for a person. Review them here.</span>
            </span>
          </span>
          <ArrowRight className="w-4 h-4 text-[#9FAAA4]" />
        </Link>
      )}

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {[
          { href: "/leads", title: "Leads", text: "All enquiries in one list, with source tags and duplicate checks." },
          { href: "/handoff", title: "Handoff queue", text: "Buyers waiting for a salesperson, with the chat so far." },
          { href: "/visits", title: "Site visits", text: "Upcoming visits, reminders and who turned up." },
        ].map((l) => (
          <Link
            key={l.href}
            href={l.href}
            className="group bg-white p-5 rounded-xl border border-[#E5E5DE] hover:border-[#C5C5BB] transition-colors"
          >
            <p className="font-heading font-semibold text-[#202B28] flex items-center justify-between">
              {l.title}
              <ArrowRight className="w-4 h-4 text-[#9FAAA4] group-hover:text-[#173B35] transition-colors" />
            </p>
            <p className="text-sm text-[#737C76] mt-1">{l.text}</p>
          </Link>
        ))}
      </div>
    </div>
  );
}
