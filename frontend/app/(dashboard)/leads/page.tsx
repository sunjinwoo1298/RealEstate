"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  Loader2,
  Plus,
  Search,
  Upload,
  Users,
  GitCompareArrows,
} from "lucide-react";
import { useAuth } from "@/lib/auth-context";
import {
  apiClient,
  ApiError,
  LeadListItem,
  LeadStatus,
  SourceType,
} from "@/lib/api-client";

const SOURCE_OPTIONS: SourceType[] = ["WEBSITE", "PROPERTY_PORTAL", "SOCIAL_AD", "HOARDING", "MANUAL", "CSV_IMPORT"];
const STATUS_OPTIONS: LeadStatus[] = [
  "NEW",
  "AI_CONTACTED",
  "QUALIFIED",
  "VISIT_REQUESTED",
  "VISIT_BOOKED",
  "VISIT_COMPLETED",
  "CONVERTED",
  "LOST",
  "OPTED_OUT",
];
const PAGE_SIZE = 20;

const STATUS_BADGE: Record<LeadStatus, string> = {
  NEW: "bg-[#E9F0F7] text-[#4779A8]",
  AI_CONTACTED: "bg-[#F0F1EC] text-[#202B28]",
  QUALIFIED: "bg-[#FDF3E7] text-[#B7791F]",
  VISIT_REQUESTED: "bg-[#FDF3E7] text-[#B7791F]",
  VISIT_BOOKED: "bg-[#E9F5EF] text-[#27845B]",
  VISIT_COMPLETED: "bg-[#E9F5EF] text-[#27845B]",
  CONVERTED: "bg-[#E9F5EF] text-[#27845B]",
  LOST: "bg-[#FDF2F2] text-[#C34D4D]",
  OPTED_OUT: "bg-[#FDF2F2] text-[#C34D4D]",
};

export default function LeadsPage() {
  const { user } = useAuth();
  const router = useRouter();

  const [leads, setLeads] = useState<LeadListItem[]>([]);
  const [total, setTotal] = useState(0);
  const [newCount, setNewCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [search, setSearch] = useState("");
  const [sourceFilter, setSourceFilter] = useState<SourceType | "">("");
  const [statusFilter, setStatusFilter] = useState<LeadStatus | "">("");
  const [page, setPage] = useState(0);

  const [showCreateForm, setShowCreateForm] = useState(false);
  const [form, setForm] = useState({ full_name: "", phone: "", email: "", campaign_name: "" });
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const loadLeads = async () => {
    setLoading(true);
    try {
      const data = await apiClient.listLeads({
        search: search || undefined,
        source: sourceFilter || undefined,
        lead_status: statusFilter || undefined,
        limit: PAGE_SIZE,
        offset: page * PAGE_SIZE,
      });
      setLeads(data.items);
      setTotal(data.total);
      setNewCount(data.new_count);
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load leads.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- intentional data fetch
    loadLeads();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search, sourceFilter, statusFilter, page]);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError(null);
    setSubmitting(true);
    try {
      await apiClient.createManualLead({
        full_name: form.full_name,
        phone: form.phone,
        email: form.email || undefined,
        campaign_name: form.campaign_name || undefined,
      });
      setForm({ full_name: "", phone: "", email: "", campaign_name: "" });
      setShowCreateForm(false);
      setPage(0);
      await loadLeads();
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : "Failed to create lead.");
    } finally {
      setSubmitting(false);
    }
  };

  if (!user) return null;

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div>
          <h1 className="text-2xl font-bold font-heading text-[#202B28] tracking-tight">Leads</h1>
          <p className="text-sm text-[#737C76] mt-1">
            {total} total &bull; {newCount} new
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Link
            href="/leads/duplicates"
            className="h-10 px-4 rounded-lg border border-[#E5E5DE] bg-white hover:bg-[#F0F1EC] text-[#202B28] text-sm font-semibold flex items-center gap-2 transition-colors"
          >
            <GitCompareArrows className="w-4 h-4" />
            Duplicate Review
          </Link>
          <Link
            href="/leads/import"
            className="h-10 px-4 rounded-lg border border-[#E5E5DE] bg-white hover:bg-[#F0F1EC] text-[#202B28] text-sm font-semibold flex items-center gap-2 transition-colors"
          >
            <Upload className="w-4 h-4" />
            Import CSV
          </Link>
          <button
            onClick={() => setShowCreateForm((v) => !v)}
            className="h-10 px-4 rounded-lg bg-[#173B35] hover:bg-[#1f4b43] text-white text-sm font-semibold flex items-center gap-2 transition-colors"
          >
            <Plus className="w-4 h-4" />
            New Lead
          </button>
        </div>
      </div>

      {showCreateForm && (
        <form
          onSubmit={handleCreate}
          className="bg-white rounded-xl border border-[#E5E5DE] shadow-xs p-6 grid grid-cols-1 md:grid-cols-4 gap-4 items-end"
        >
          <div>
            <label className="block text-xs font-semibold text-[#202B28] mb-1.5">Full name</label>
            <input
              required
              value={form.full_name}
              onChange={(e) => setForm({ ...form, full_name: e.target.value })}
              className="w-full h-10 px-3 rounded-lg border border-[#E5E5DE] text-sm focus:outline-none focus:ring-2 focus:ring-[#315C50]"
            />
          </div>
          <div>
            <label className="block text-xs font-semibold text-[#202B28] mb-1.5">Phone</label>
            <input
              required
              value={form.phone}
              onChange={(e) => setForm({ ...form, phone: e.target.value })}
              placeholder="9876543210"
              className="w-full h-10 px-3 rounded-lg border border-[#E5E5DE] text-sm focus:outline-none focus:ring-2 focus:ring-[#315C50]"
            />
          </div>
          <div>
            <label className="block text-xs font-semibold text-[#202B28] mb-1.5">Email (optional)</label>
            <input
              type="email"
              value={form.email}
              onChange={(e) => setForm({ ...form, email: e.target.value })}
              className="w-full h-10 px-3 rounded-lg border border-[#E5E5DE] text-sm focus:outline-none focus:ring-2 focus:ring-[#315C50]"
            />
          </div>
          <div>
            <label className="block text-xs font-semibold text-[#202B28] mb-1.5">Project interest (optional)</label>
            <input
              value={form.campaign_name}
              onChange={(e) => setForm({ ...form, campaign_name: e.target.value })}
              className="w-full h-10 px-3 rounded-lg border border-[#E5E5DE] text-sm focus:outline-none focus:ring-2 focus:ring-[#315C50]"
            />
          </div>
          {formError && <p className="md:col-span-4 text-sm text-[#C34D4D]">{formError}</p>}
          <div className="md:col-span-4">
            <button
              type="submit"
              disabled={submitting}
              className="h-10 px-4 rounded-lg bg-[#315C50] hover:bg-[#3c6e60] disabled:opacity-60 text-white text-sm font-semibold flex items-center gap-2"
            >
              {submitting && <Loader2 className="w-4 h-4 animate-spin" />}
              Create lead
            </button>
          </div>
        </form>
      )}

      <div className="bg-white rounded-xl border border-[#E5E5DE] shadow-xs">
        <div className="px-6 py-4 border-b border-[#E5E5DE] flex items-center gap-3 flex-wrap">
          <div className="relative flex-1 min-w-[200px]">
            <Search className="w-4 h-4 text-[#9EA69F] absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              value={search}
              onChange={(e) => {
                setPage(0);
                setSearch(e.target.value);
              }}
              placeholder="Search by name, phone or email"
              className="w-full h-10 pl-9 pr-3 rounded-lg border border-[#E5E5DE] text-sm focus:outline-none focus:ring-2 focus:ring-[#315C50]"
            />
          </div>
          <select
            value={sourceFilter}
            onChange={(e) => {
              setPage(0);
              setSourceFilter(e.target.value as SourceType | "");
            }}
            className="h-10 px-3 rounded-lg border border-[#E5E5DE] text-sm bg-white focus:outline-none focus:ring-2 focus:ring-[#315C50]"
          >
            <option value="">All sources</option>
            {SOURCE_OPTIONS.map((s) => (
              <option key={s} value={s}>
                {s.replace("_", " ")}
              </option>
            ))}
          </select>
          <select
            value={statusFilter}
            onChange={(e) => {
              setPage(0);
              setStatusFilter(e.target.value as LeadStatus | "");
            }}
            className="h-10 px-3 rounded-lg border border-[#E5E5DE] text-sm bg-white focus:outline-none focus:ring-2 focus:ring-[#315C50]"
          >
            <option value="">All statuses</option>
            {STATUS_OPTIONS.map((s) => (
              <option key={s} value={s}>
                {s.replace(/_/g, " ")}
              </option>
            ))}
          </select>
        </div>

        {error && <p className="px-6 py-4 text-sm text-[#C34D4D]">{error}</p>}

        {loading ? (
          <div className="px-6 py-10 text-center text-sm text-[#737C76] flex items-center justify-center gap-2">
            <Loader2 className="w-4 h-4 animate-spin" />
            Loading leads...
          </div>
        ) : leads.length === 0 ? (
          <div className="px-6 py-12 text-center">
            <Users className="w-8 h-8 text-[#C5C5BB] mx-auto mb-3" />
            <p className="text-sm text-[#737C76]">No leads match your filters yet.</p>
          </div>
        ) : (
          <>
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs font-semibold text-[#737C76] uppercase tracking-wider border-b border-[#E5E5DE]">
                  <th className="px-6 py-3">Buyer</th>
                  <th className="px-6 py-3">Phone</th>
                  <th className="px-6 py-3">Source</th>
                  <th className="px-6 py-3">Status</th>
                  <th className="px-6 py-3">Created</th>
                </tr>
              </thead>
              <tbody>
                {leads.map((lead) => (
                  <tr
                    key={lead.id}
                    onClick={() => router.push(`/leads/${lead.id}`)}
                    className="border-b border-[#F0F1EC] last:border-0 cursor-pointer hover:bg-[#F7F6F2]"
                  >
                    <td className="px-6 py-3 font-medium text-[#202B28]">{lead.full_name}</td>
                    <td className="px-6 py-3 text-[#737C76]">{lead.normalized_phone || "—"}</td>
                    <td className="px-6 py-3 text-[#737C76]">
                      {lead.latest_source_type ? lead.latest_source_type.replace("_", " ") : "—"}
                      {lead.source_count > 1 && (
                        <span className="ml-1 text-xs text-[#9EA69F]">(+{lead.source_count - 1})</span>
                      )}
                    </td>
                    <td className="px-6 py-3">
                      <span className={`text-xs font-semibold px-2 py-1 rounded-md ${STATUS_BADGE[lead.lead_status]}`}>
                        {lead.lead_status.replace(/_/g, " ")}
                      </span>
                    </td>
                    <td className="px-6 py-3 text-[#737C76]">{new Date(lead.created_at).toLocaleDateString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div className="px-6 py-4 flex items-center justify-between text-sm text-[#737C76]">
              <span>
                Page {page + 1} of {totalPages}
              </span>
              <div className="flex gap-2">
                <button
                  disabled={page === 0}
                  onClick={() => setPage((p) => Math.max(0, p - 1))}
                  className="h-8 px-3 rounded-md border border-[#E5E5DE] disabled:opacity-40"
                >
                  Previous
                </button>
                <button
                  disabled={page + 1 >= totalPages}
                  onClick={() => setPage((p) => p + 1)}
                  className="h-8 px-3 rounded-md border border-[#E5E5DE] disabled:opacity-40"
                >
                  Next
                </button>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
