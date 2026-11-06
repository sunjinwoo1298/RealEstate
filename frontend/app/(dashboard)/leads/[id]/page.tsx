"use client";

import React, { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { ArrowLeft, Loader2, Mail, Phone, Globe } from "lucide-react";
import { apiClient, ApiError, LeadDetail, LeadStatus } from "@/lib/api-client";

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

export default function LeadDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();

  const [lead, setLead] = useState<LeadDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [updating, setUpdating] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const data = await apiClient.getLead(params.id);
      setLead(data);
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load lead.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- intentional data fetch
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params.id]);

  const handleStatusChange = async (status: LeadStatus) => {
    if (!lead) return;
    setUpdating(true);
    try {
      const updated = await apiClient.updateLead(lead.id, { lead_status: status });
      setLead(updated);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to update lead status.");
    } finally {
      setUpdating(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20 text-sm text-[#737C76] gap-2">
        <Loader2 className="w-4 h-4 animate-spin" />
        Loading lead...
      </div>
    );
  }

  if (error && !lead) {
    return <p className="text-sm text-[#C34D4D]">{error}</p>;
  }

  if (!lead) return null;

  return (
    <div className="space-y-6">
      <button
        onClick={() => router.push("/leads")}
        className="flex items-center gap-1.5 text-sm text-[#737C76] hover:text-[#202B28]"
      >
        <ArrowLeft className="w-4 h-4" />
        Back to leads
      </button>

      <div className="bg-white rounded-xl border border-[#E5E5DE] shadow-xs p-6">
        <div className="flex items-start justify-between flex-wrap gap-4">
          <div>
            <h1 className="text-2xl font-bold font-heading text-[#202B28] tracking-tight">{lead.full_name}</h1>
            <div className="flex items-center gap-4 mt-2 text-sm text-[#737C76]">
              <span className="flex items-center gap-1.5">
                <Phone className="w-3.5 h-3.5" />
                {lead.normalized_phone || "No phone on file"}
              </span>
              <span className="flex items-center gap-1.5">
                <Mail className="w-3.5 h-3.5" />
                {lead.normalized_email || "No email on file"}
              </span>
            </div>
          </div>
          <select
            value={lead.lead_status}
            disabled={updating}
            onChange={(e) => handleStatusChange(e.target.value as LeadStatus)}
            className="h-10 px-3 rounded-lg border border-[#E5E5DE] text-sm bg-white focus:outline-none focus:ring-2 focus:ring-[#315C50] disabled:opacity-60"
          >
            {STATUS_OPTIONS.map((s) => (
              <option key={s} value={s}>
                {s.replace(/_/g, " ")}
              </option>
            ))}
          </select>
        </div>

        {error && <p className="mt-4 text-sm text-[#C34D4D]">{error}</p>}

        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-6 pt-6 border-t border-[#F0F1EC]">
          <div>
            <p className="text-xs text-[#737C76] mb-1">Consent</p>
            <p className="text-sm font-medium text-[#202B28]">{lead.consent_status.replace(/_/g, " ")}</p>
          </div>
          <div>
            <p className="text-xs text-[#737C76] mb-1">Preferred language</p>
            <p className="text-sm font-medium text-[#202B28]">{lead.preferred_language || "—"}</p>
          </div>
          <div>
            <p className="text-xs text-[#737C76] mb-1">Created</p>
            <p className="text-sm font-medium text-[#202B28]">{new Date(lead.created_at).toLocaleString()}</p>
          </div>
          <div>
            <p className="text-xs text-[#737C76] mb-1">Enquiries on file</p>
            <p className="text-sm font-medium text-[#202B28]">{lead.sources.length}</p>
          </div>
        </div>
      </div>

      <div className="bg-white rounded-xl border border-[#E5E5DE] shadow-xs">
        <div className="px-6 py-4 border-b border-[#E5E5DE] flex items-center gap-2">
          <Globe className="w-4 h-4 text-[#173B35]" />
          <h2 className="text-sm font-semibold text-[#202B28]">Source & enquiry history</h2>
        </div>
        {lead.sources.length === 0 ? (
          <p className="px-6 py-8 text-center text-sm text-[#737C76]">No enquiries recorded yet.</p>
        ) : (
          <ul className="divide-y divide-[#F0F1EC]">
            {lead.sources.map((source) => (
              <li key={source.id} className="px-6 py-4 flex items-center justify-between flex-wrap gap-2">
                <div>
                  <p className="text-sm font-medium text-[#202B28]">{source.source_type.replace(/_/g, " ")}</p>
                  <p className="text-xs text-[#737C76] mt-0.5">
                    {source.campaign_name || "No campaign recorded"}
                    {source.external_lead_id ? ` • Ref: ${source.external_lead_id}` : ""}
                  </p>
                </div>
                <span className="text-xs text-[#9EA69F]">
                  {new Date(source.submitted_at).toLocaleString()}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
