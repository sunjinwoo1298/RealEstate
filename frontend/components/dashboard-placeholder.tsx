"use client";

import React, { useEffect, useState } from "react";
import { apiClient, HealthResponse, OverviewAnalytics } from "@/lib/api-client";
import {
  Users,
  CalendarCheck,
  Sparkles,
  TrendingUp,
  Database,
  Server,
  Zap,
  ArrowUpRight,
  ShieldAlert,
  Clock,
  Layers,
} from "lucide-react";

export function DashboardPlaceholder() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [overview, setOverview] = useState<OverviewAnalytics | null>(null);

  useEffect(() => {
    apiClient
      .getHealth()
      .then((data) => setHealth(data))
      .catch(() => setHealth(null))
      .finally(() => setLoading(false));
    apiClient
      .getOverviewAnalytics({ range: "LAST_30_DAYS" })
      .then((data) => setOverview(data))
      .catch(() => setOverview(null));
  }, []);

  const redisHealthy = health?.redis?.status === "healthy" || health?.redis?.status === "connected";
  const formatPercent = (v: number | null | undefined) => (v === null || v === undefined ? "--" : `${v}%`);

  return (
    <div className="space-y-6">
      {/* Welcome Banner */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 bg-white p-6 rounded-xl border border-[#E5E5DE] shadow-xs">
        <div>
          <h1 className="text-2xl font-bold font-heading text-[#202B28] tracking-tight">
            EstateFlow AI Platform
          </h1>
          <p className="text-sm text-[#737C76] mt-1">
            Real-estate sales automation, lead deduplication & site-visit scheduling engine.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-xs px-3 py-1.5 rounded-lg bg-[#173B35] text-white font-medium shadow-xs">
            FastAPI + Next.js
          </span>
        </div>
      </div>

      {/* KPI Stats Cards - 12-column grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Card 1 */}
        <div className="bg-white p-5 rounded-xl border border-[#E5E5DE] shadow-xs hover:border-[#C5C5BB] transition-colors">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-[#737C76] uppercase tracking-wider">
              Total Enquiries
            </span>
            <div className="w-8 h-8 rounded-lg bg-[#F0F1EC] flex items-center justify-center text-[#173B35]">
              <Users className="w-4 h-4" />
            </div>
          </div>
          <div className="mt-3">
            <span className="text-3xl font-bold font-heading text-[#202B28]">{overview ? overview.total_unique_leads : "--"}</span>
            <div className="flex items-center gap-1.5 text-xs text-[#27845B] mt-1 font-medium">
              <ArrowUpRight className="w-3.5 h-3.5" />
              <span>Unique leads, last 30 days</span>
            </div>
          </div>
        </div>

        {/* Card 2 */}
        <div className="bg-white p-5 rounded-xl border border-[#E5E5DE] shadow-xs hover:border-[#C5C5BB] transition-colors">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-[#737C76] uppercase tracking-wider">
              Qualification Rate
            </span>
            <div className="w-8 h-8 rounded-lg bg-[#E9F5EF] flex items-center justify-center text-[#27845B]">
              <Sparkles className="w-4 h-4" />
            </div>
          </div>
          <div className="mt-3">
            <span className="text-3xl font-bold font-heading text-[#202B28]">{formatPercent(overview?.qualification_rate_percent)}</span>
            <div className="flex items-center gap-1.5 text-xs text-[#737C76] mt-1 font-medium">
              <span>Of unique leads, last 30 days</span>
            </div>
          </div>
        </div>

        {/* Card 3 */}
        <div className="bg-white p-5 rounded-xl border border-[#E5E5DE] shadow-xs hover:border-[#C5C5BB] transition-colors">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-[#737C76] uppercase tracking-wider">
              Site Visits Booked
            </span>
            <div className="w-8 h-8 rounded-lg bg-[#FEF7EC] flex items-center justify-center text-[#B7791F]">
              <CalendarCheck className="w-4 h-4" />
            </div>
          </div>
          <div className="mt-3">
            <span className="text-3xl font-bold font-heading text-[#202B28]">{overview ? overview.site_visits_booked : "--"}</span>
            <div className="flex items-center gap-1.5 text-xs text-[#737C76] mt-1 font-medium">
              <span>Booked in the last 30 days</span>
            </div>
          </div>
        </div>

        {/* Card 4 */}
        <div className="bg-white p-5 rounded-xl border border-[#E5E5DE] shadow-xs hover:border-[#C5C5BB] transition-colors">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-[#737C76] uppercase tracking-wider">
              Show-Up Rate
            </span>
            <div className="w-8 h-8 rounded-lg bg-[#F0F1EC] flex items-center justify-center text-[#C47A55]">
              <TrendingUp className="w-4 h-4 text-[#C47A55]" />
            </div>
          </div>
          <div className="mt-3">
            <span className="text-3xl font-bold font-heading text-[#202B28]">{formatPercent(overview?.attendance_rate_percent)}</span>
            <div className="flex items-center gap-1.5 text-xs text-[#737C76] mt-1 font-medium">
              <span>Of past visits, last 30 days</span>
            </div>
          </div>
        </div>
      </div>

      {/* Main Grid: Infrastructure Verification & System Architecture */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* System Health Card (7 cols) */}
        <div className="lg:col-span-7 bg-white rounded-xl border border-[#E5E5DE] p-6 shadow-xs">
          <div className="flex items-center justify-between pb-4 border-b border-[#E5E5DE]">
            <div>
              <h2 className="text-lg font-bold font-heading text-[#202B28]">
                Foundation Environment Health
              </h2>
              <p className="text-xs text-[#737C76] mt-0.5">
                Real-time connectivity to FastAPI backend, hosted PostgreSQL, and Redis
              </p>
            </div>
            <div className="flex items-center gap-2">
              <span className="inline-block w-2.5 h-2.5 rounded-full bg-[#27845B] animate-pulse" />
              <span className="text-xs font-semibold text-[#27845B]">Live</span>
            </div>
          </div>

          <div className="mt-5 space-y-4">
            {/* FastAPI Backend */}
            <div className="p-4 rounded-lg bg-[#F7F6F2] border border-[#E5E5DE] flex items-start justify-between">
              <div className="flex items-start gap-3">
                <div className="w-9 h-9 rounded-md bg-[#173B35] text-white flex items-center justify-center shrink-0">
                  <Server className="w-4 h-4" />
                </div>
                <div>
                  <h3 className="text-sm font-semibold text-[#202B28]">
                    FastAPI Application Server
                  </h3>
                  <p className="text-xs text-[#737C76] mt-0.5">
                    Port 8000 &bull; Centralized Pydantic Settings &bull; Alembic Migrations
                  </p>
                  <span className="inline-block mt-2 text-[11px] font-mono bg-white px-2 py-0.5 rounded border border-[#E5E5DE] text-[#173B35]">
                    GET /api/v1/health
                  </span>
                </div>
              </div>
              <span className="text-xs font-semibold px-2.5 py-1 rounded-md bg-[#E9F5EF] text-[#27845B] border border-[#C5E6D5]">
                {loading ? "Checking..." : health ? "Online" : "Connecting..."}
              </span>
            </div>

            {/* Prisma Postgres */}
            <div className="p-4 rounded-lg bg-[#F7F6F2] border border-[#E5E5DE] flex items-start justify-between">
              <div className="flex items-start gap-3">
                <div className="w-9 h-9 rounded-md bg-[#315C50] text-white flex items-center justify-center shrink-0">
                  <Database className="w-4 h-4" />
                </div>
                <div>
                  <h3 className="text-sm font-semibold text-[#202B28]">
                    Hosted Prisma Postgres
                  </h3>
                  <p className="text-xs text-[#737C76] mt-0.5">
                    SQLAlchemy AsyncEngine + asyncpg &bull; Credentials backend-only
                  </p>
                  {health?.database?.latency_ms && (
                    <span className="inline-flex items-center gap-1 mt-2 text-[11px] text-[#737C76]">
                      <Clock className="w-3 h-3" />
                      Roundtrip latency: {health.database.latency_ms} ms
                    </span>
                  )}
                </div>
              </div>
              <span className="text-xs font-semibold px-2.5 py-1 rounded-md bg-[#E9F5EF] text-[#27845B] border border-[#C5E6D5]">
                {loading
                  ? "Checking..."
                  : health?.database?.status === "healthy"
                    ? "Connected"
                    : "Unavailable"}
              </span>
            </div>

            {/* Redis */}
            <div className="p-4 rounded-lg bg-[#F7F6F2] border border-[#E5E5DE] flex items-start justify-between">
              <div className="flex items-start gap-3">
                <div className="w-9 h-9 rounded-md bg-[#C47A55] text-white flex items-center justify-center shrink-0">
                  <Zap className="w-4 h-4" />
                </div>
                <div>
                  <h3 className="text-sm font-semibold text-[#202B28]">
                    Redis Integration Module
                  </h3>
                  <p className="text-xs text-[#737C76] mt-0.5">
                    Rate limiting &amp; AI processing lock &bull; Fails open when unavailable
                  </p>
                </div>
              </div>
              <span className="text-xs font-semibold px-2.5 py-1 rounded-md bg-[#F0F1EC] text-[#737C76] border border-[#E5E5DE]">
                {loading ? "Checking..." : redisHealthy ? "Connected" : "Unavailable"}
              </span>
            </div>
          </div>
        </div>

        {/* Project Context & Architectural Rules (5 cols) */}
        <div className="lg:col-span-5 bg-white rounded-xl border border-[#E5E5DE] p-6 shadow-xs flex flex-col justify-between">
          <div>
            <h2 className="text-lg font-bold font-heading text-[#202B28]">
              Architectural Invariants
            </h2>
            <p className="text-xs text-[#737C76] mt-0.5">
              Strict rules enforced from <code className="text-[#173B35]">AGENT.md</code>
            </p>

            <ul className="mt-4 space-y-3 text-xs text-[#202B28]">
              <li className="flex items-start gap-2.5">
                <span className="w-5 h-5 rounded-full bg-[#E9F5EF] text-[#27845B] flex items-center justify-center font-bold text-[10px] shrink-0 mt-0.5">
                  1
                </span>
                <span>
                  <strong>PostgreSQL is the single source of truth</strong> for all business data.
                </span>
              </li>
              <li className="flex items-start gap-2.5">
                <span className="w-5 h-5 rounded-full bg-[#E9F5EF] text-[#27845B] flex items-center justify-center font-bold text-[10px] shrink-0 mt-0.5">
                  2
                </span>
                <span>
                  <strong>Database credentials remain backend-only.</strong> Frontend never accesses database directly.
                </span>
              </li>
              <li className="flex items-start gap-2.5">
                <span className="w-5 h-5 rounded-full bg-[#E9F5EF] text-[#27845B] flex items-center justify-center font-bold text-[10px] shrink-0 mt-0.5">
                  3
                </span>
                <span>
                  <strong>AI orchestration</strong> never executes arbitrary SQL or bypasses domain services.
                </span>
              </li>
              <li className="flex items-start gap-2.5">
                <span className="w-5 h-5 rounded-full bg-[#E9F5EF] text-[#27845B] flex items-center justify-center font-bold text-[10px] shrink-0 mt-0.5">
                  4
                </span>
                <span>
                  <strong>Atomic, concurrency-safe booking:</strong> confirmations only after database commit.
                </span>
              </li>
            </ul>
          </div>

          <div className="mt-6 pt-4 border-t border-[#E5E5DE] flex items-center justify-between text-xs text-[#737C76]">
            <span>EstateFlow AI v1.0.0</span>
            <span className="font-medium text-[#173B35]">Production workflow active</span>
          </div>
        </div>
      </div>
    </div>
  );
}

