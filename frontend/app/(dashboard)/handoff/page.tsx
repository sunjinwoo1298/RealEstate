"use client";

import React, { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Headset, Loader2, Users } from "lucide-react";
import { useAuth } from "@/lib/auth-context";
import { apiClient, ApiError, HandoffListItem, HandoffStatus } from "@/lib/api-client";

const PAGE_SIZE = 20;

const STATUS_BADGE: Record<HandoffStatus, string> = {
  PENDING: "bg-[#FDF6EC] text-[#B9772F]",
  ASSIGNED: "bg-[#EDEFF8] text-[#3C4EA3]",
  ACCEPTED: "bg-[#E9F5EF] text-[#27845B]",
  RESOLVED: "bg-[#F0F1EC] text-[#202B28]",
  CANCELLED: "bg-[#FDF2F2] text-[#C34D4D]",
};

const REASON_LABEL: Record<string, string> = {
  BUYER_REQUEST: "Buyer requested",
  UNSUPPORTED_QUERY: "Unsupported query",
  LOW_CONFIDENCE: "Low confidence",
  COMPLAINT: "Complaint",
  OTHER: "Other",
};

function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString("en-IN", { timeZone: "Asia/Kolkata", dateStyle: "medium", timeStyle: "short" });
}

export default function HandoffQueuePage() {
  const { user } = useAuth();
  const router = useRouter();

  const [handoffs, setHandoffs] = useState<HandoffListItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<HandoffStatus | "">("PENDING");
  const [mineOnly, setMineOnly] = useState(false);
  const [page, setPage] = useState(0);

  const load = async () => {
    setLoading(true);
    try {
      const data = await apiClient.listHandoffs({
        status: statusFilter || undefined,
        mine: mineOnly,
        limit: PAGE_SIZE,
        offset: page * PAGE_SIZE,
      });
      setHandoffs(data.items);
      setTotal(data.total);
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load handoffs.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- intentional data fetch
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [statusFilter, mineOnly, page]);

  if (!user) return null;

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div>
          <h1 className="text-2xl font-bold font-heading text-[#202B28] tracking-tight">Handoff Queue</h1>
          <p className="text-sm text-[#737C76] mt-1">{total} total</p>
        </div>
        <div className="flex items-center gap-3">
          <label className="flex items-center gap-2 text-sm text-[#202B28]">
            <input
              type="checkbox"
              checked={mineOnly}
              onChange={(e) => {
                setPage(0);
                setMineOnly(e.target.checked);
              }}
              className="accent-[#173B35]"
            />
            My assigned only
          </label>
          <select
            value={statusFilter}
            onChange={(e) => {
              setPage(0);
              setStatusFilter(e.target.value as HandoffStatus | "");
            }}
            className="h-10 px-3 rounded-lg border border-[#E5E5DE] text-sm bg-white focus:outline-none focus:ring-2 focus:ring-[#315C50]"
          >
            <option value="">All statuses</option>
            <option value="PENDING">Pending</option>
            <option value="ASSIGNED">Assigned</option>
            <option value="ACCEPTED">Accepted</option>
            <option value="RESOLVED">Resolved</option>
            <option value="CANCELLED">Cancelled</option>
          </select>
        </div>
      </div>

      <div className="bg-white rounded-xl border border-[#E5E5DE] shadow-xs">
        {error && <p className="px-6 py-4 text-sm text-[#C34D4D]">{error}</p>}

        {loading ? (
          <div className="px-6 py-10 text-center text-sm text-[#737C76] flex items-center justify-center gap-2">
            <Loader2 className="w-4 h-4 animate-spin" />
            Loading handoffs...
          </div>
        ) : handoffs.length === 0 ? (
          <div className="px-6 py-12 text-center">
            <Users className="w-8 h-8 text-[#C5C5BB] mx-auto mb-3" />
            <p className="text-sm text-[#737C76]">No handoffs found.</p>
          </div>
        ) : (
          <>
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs font-semibold text-[#737C76] uppercase tracking-wider border-b border-[#E5E5DE]">
                  <th className="px-6 py-3">Buyer</th>
                  <th className="px-6 py-3">Phone</th>
                  <th className="px-6 py-3">Reason</th>
                  <th className="px-6 py-3">Status</th>
                  <th className="px-6 py-3">Requested</th>
                </tr>
              </thead>
              <tbody>
                {handoffs.map((handoff) => (
                  <tr
                    key={handoff.id}
                    onClick={() => router.push(`/handoff/${handoff.id}`)}
                    className="border-b border-[#F0F1EC] last:border-0 cursor-pointer hover:bg-[#F7F6F2]"
                  >
                    <td className="px-6 py-3 font-medium text-[#202B28] flex items-center gap-2">
                      <Headset className="w-3.5 h-3.5 text-[#9EA69F]" />
                      {handoff.lead_full_name}
                    </td>
                    <td className="px-6 py-3 text-[#737C76]">{handoff.lead_normalized_phone || "—"}</td>
                    <td className="px-6 py-3 text-[#737C76]">{REASON_LABEL[handoff.reason] || handoff.reason}</td>
                    <td className="px-6 py-3">
                      <span className={`text-xs font-semibold px-2 py-1 rounded-md ${STATUS_BADGE[handoff.status]}`}>
                        {handoff.status}
                      </span>
                    </td>
                    <td className="px-6 py-3 text-[#737C76]">{formatDateTime(handoff.created_at)}</td>
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
