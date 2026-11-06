"use client";

import React, { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Loader2, MessageSquare } from "lucide-react";
import { useAuth } from "@/lib/auth-context";
import { apiClient, ApiError, ConversationListItem, ConversationStatus } from "@/lib/api-client";

const PAGE_SIZE = 20;

const STATUS_BADGE: Record<ConversationStatus, string> = {
  ACTIVE: "bg-[#E9F5EF] text-[#27845B]",
  CLOSED: "bg-[#F0F1EC] text-[#202B28]",
};

const OWNERSHIP_LABEL: Record<string, string> = {
  AI_ACTIVE: "AI Active",
  PENDING_ASSIGNMENT: "Pending Assignment",
  HUMAN_ACTIVE: "Staff Active",
  RESOLVED: "Resolved",
};

export default function ConversationsPage() {
  const { user } = useAuth();
  const router = useRouter();

  const [conversations, setConversations] = useState<ConversationListItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<ConversationStatus | "">("");
  const [page, setPage] = useState(0);

  const load = async () => {
    setLoading(true);
    try {
      const data = await apiClient.listConversations({
        status: statusFilter || undefined,
        limit: PAGE_SIZE,
        offset: page * PAGE_SIZE,
      });
      setConversations(data.items);
      setTotal(data.total);
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load conversations.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- intentional data fetch
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [statusFilter, page]);

  if (!user) return null;

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div>
          <h1 className="text-2xl font-bold font-heading text-[#202B28] tracking-tight">Conversations</h1>
          <p className="text-sm text-[#737C76] mt-1">{total} total</p>
        </div>
        <select
          value={statusFilter}
          onChange={(e) => {
            setPage(0);
            setStatusFilter(e.target.value as ConversationStatus | "");
          }}
          className="h-10 px-3 rounded-lg border border-[#E5E5DE] text-sm bg-white focus:outline-none focus:ring-2 focus:ring-[#315C50]"
        >
          <option value="">All statuses</option>
          <option value="ACTIVE">Active</option>
          <option value="CLOSED">Closed</option>
        </select>
      </div>

      <div className="bg-white rounded-xl border border-[#E5E5DE] shadow-xs">
        {error && <p className="px-6 py-4 text-sm text-[#C34D4D]">{error}</p>}

        {loading ? (
          <div className="px-6 py-10 text-center text-sm text-[#737C76] flex items-center justify-center gap-2">
            <Loader2 className="w-4 h-4 animate-spin" />
            Loading conversations...
          </div>
        ) : conversations.length === 0 ? (
          <div className="px-6 py-12 text-center">
            <MessageSquare className="w-8 h-8 text-[#C5C5BB] mx-auto mb-3" />
            <p className="text-sm text-[#737C76]">No conversations yet.</p>
          </div>
        ) : (
          <>
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs font-semibold text-[#737C76] uppercase tracking-wider border-b border-[#E5E5DE]">
                  <th className="px-6 py-3">Buyer</th>
                  <th className="px-6 py-3">Phone</th>
                  <th className="px-6 py-3">Language</th>
                  <th className="px-6 py-3">State</th>
                  <th className="px-6 py-3">Ownership</th>
                  <th className="px-6 py-3">Status</th>
                  <th className="px-6 py-3">Last activity</th>
                </tr>
              </thead>
              <tbody>
                {conversations.map((conversation) => (
                  <tr
                    key={conversation.id}
                    onClick={() => router.push(`/conversations/${conversation.id}`)}
                    className="border-b border-[#F0F1EC] last:border-0 cursor-pointer hover:bg-[#F7F6F2]"
                  >
                    <td className="px-6 py-3 font-medium text-[#202B28]">{conversation.lead_full_name}</td>
                    <td className="px-6 py-3 text-[#737C76]">{conversation.lead_normalized_phone || "—"}</td>
                    <td className="px-6 py-3 text-[#737C76]">{conversation.language}</td>
                    <td className="px-6 py-3 text-[#737C76]">{conversation.conversation_state.replace(/_/g, " ")}</td>
                    <td className="px-6 py-3 text-[#737C76]">{OWNERSHIP_LABEL[conversation.ownership_status]}</td>
                    <td className="px-6 py-3">
                      <span className={`text-xs font-semibold px-2 py-1 rounded-md ${STATUS_BADGE[conversation.status]}`}>
                        {conversation.status}
                      </span>
                    </td>
                    <td className="px-6 py-3 text-[#737C76]">
                      {conversation.last_message_at
                        ? new Date(conversation.last_message_at).toLocaleString()
                        : "—"}
                    </td>
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
