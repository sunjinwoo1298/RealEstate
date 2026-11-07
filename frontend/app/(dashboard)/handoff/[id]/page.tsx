"use client";

import React, { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { ArrowLeft, Loader2, Mail, Phone, Send, UserCheck } from "lucide-react";
import {
  apiClient,
  ApiError,
  HandoffDetail,
  MessagePublic,
  UserPublic,
} from "@/lib/api-client";
import { useAuth } from "@/lib/auth-context";

const SENDER_LABEL: Record<string, string> = {
  BUYER: "Buyer",
  AI: "AI",
  STAFF: "Staff",
  SYSTEM: "System",
};

function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString("en-IN", { timeZone: "Asia/Kolkata", dateStyle: "medium", timeStyle: "short" });
}

export default function HandoffWorkspacePage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const { user } = useAuth();

  const [handoff, setHandoff] = useState<HandoffDetail | null>(null);
  const [messages, setMessages] = useState<MessagePublic[]>([]);
  const [executives, setExecutives] = useState<UserPublic[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionPending, setActionPending] = useState(false);
  const [reply, setReply] = useState("");
  const [sending, setSending] = useState(false);
  const [reassignTo, setReassignTo] = useState("");

  const load = async () => {
    try {
      const data = await apiClient.getHandoff(params.id);
      setHandoff(data);
      const messagesData = await apiClient.getConversationMessages(data.conversation_id, { limit: 100 });
      setMessages(messagesData.items);
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load handoff.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- intentional data fetch on mount
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params.id]);

  useEffect(() => {
    (async () => {
      try {
        const data = await apiClient.listStaffUsers();
        setExecutives(data.items.filter((u) => u.role === "SALES_EXECUTIVE" && u.is_active));
      } catch {
        // The executive dropdown is only needed for manager/admin reassignment; leave it empty on failure.
      }
    })();
  }, []);

  if (!user) return null;

  const isManagerOrAdmin = user.role === "MANAGER" || user.role === "ADMIN";
  const isAssignedExecutive = handoff?.assigned_executive_id === user.id;

  const runAction = async (action: () => Promise<void>) => {
    setActionPending(true);
    setActionError(null);
    try {
      await action();
      await load();
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : "Action failed.");
    } finally {
      setActionPending(false);
    }
  };

  const handleSendReply = async () => {
    if (!handoff || !reply.trim()) return;
    setSending(true);
    setActionError(null);
    try {
      await apiClient.sendStaffMessage(handoff.conversation_id, reply.trim());
      setReply("");
      const messagesData = await apiClient.getConversationMessages(handoff.conversation_id, { limit: 100 });
      setMessages(messagesData.items);
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : "Failed to send reply.");
    } finally {
      setSending(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20 text-sm text-[#737C76] gap-2">
        <Loader2 className="w-4 h-4 animate-spin" />
        Loading handoff...
      </div>
    );
  }

  if (error || !handoff) {
    return <p className="text-sm text-[#C34D4D]">{error || "Handoff not found."}</p>;
  }

  const canReply = handoff.conversation_ownership_status === "HUMAN_ACTIVE" && (isManagerOrAdmin || isAssignedExecutive);

  return (
    <div className="space-y-6">
      <button
        onClick={() => router.push("/handoff")}
        className="flex items-center gap-1.5 text-sm text-[#737C76] hover:text-[#202B28] transition-colors"
      >
        <ArrowLeft className="w-4 h-4" />
        Back to handoff queue
      </button>

      {actionError && <p className="text-sm text-[#C34D4D]">{actionError}</p>}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-1 space-y-4">
          <div className="bg-white rounded-xl border border-[#E5E5DE] shadow-xs p-6 space-y-4">
            <div>
              <h1 className="text-lg font-bold font-heading text-[#202B28]">{handoff.lead_full_name}</h1>
              <div className="flex items-center gap-2 mt-2">
                <span className="text-xs font-semibold px-2 py-1 rounded-md bg-[#EDEFF8] text-[#3C4EA3]">
                  {handoff.status}
                </span>
                <span className="text-xs font-semibold px-2 py-1 rounded-md bg-[#F0F1EC] text-[#202B28]">
                  {handoff.reason.replace(/_/g, " ")}
                </span>
              </div>
            </div>
            <div className="space-y-2 text-sm text-[#737C76]">
              {handoff.lead_normalized_phone && (
                <div className="flex items-center gap-2">
                  <Phone className="w-4 h-4 text-[#9EA69F]" />
                  {handoff.lead_normalized_phone}
                </div>
              )}
              {handoff.lead_normalized_email && (
                <div className="flex items-center gap-2">
                  <Mail className="w-4 h-4 text-[#9EA69F]" />
                  {handoff.lead_normalized_email}
                </div>
              )}
              {handoff.source_types.length > 0 && (
                <div>Source: {handoff.source_types.join(", ")}</div>
              )}
              {handoff.lead_preferred_language && <div>Preferred language: {handoff.lead_preferred_language}</div>}
            </div>

            {handoff.summary && (
              <div className="pt-4 border-t border-[#F0F1EC]">
                <p className="text-xs font-semibold text-[#202B28] mb-1.5">Escalation summary</p>
                <p className="text-sm text-[#737C76] whitespace-pre-wrap">{handoff.summary}</p>
              </div>
            )}

            {handoff.qualification && (
              <div className="pt-4 border-t border-[#F0F1EC] space-y-1.5 text-sm">
                <p className="text-xs font-semibold text-[#202B28] mb-1.5">Qualification</p>
                {handoff.qualification.configuration && (
                  <div className="flex justify-between">
                    <span className="text-[#737C76]">Configuration</span>
                    <span className="font-medium text-[#202B28]">{handoff.qualification.configuration}</span>
                  </div>
                )}
                {(handoff.qualification.budget_min || handoff.qualification.budget_max) && (
                  <div className="flex justify-between">
                    <span className="text-[#737C76]">Budget</span>
                    <span className="font-medium text-[#202B28]">
                      {handoff.qualification.budget_min ?? "—"} – {handoff.qualification.budget_max ?? "—"}
                    </span>
                  </div>
                )}
                {handoff.qualification.purchase_purpose && (
                  <div className="flex justify-between">
                    <span className="text-[#737C76]">Purpose</span>
                    <span className="font-medium text-[#202B28]">{handoff.qualification.purchase_purpose}</span>
                  </div>
                )}
                {handoff.qualification.preferred_visit_date && (
                  <div className="flex justify-between">
                    <span className="text-[#737C76]">Wants to visit</span>
                    <span className="font-medium text-[#202B28]">{handoff.qualification.preferred_visit_date}</span>
                  </div>
                )}
              </div>
            )}

            {handoff.site_visits.length > 0 && (
              <div className="pt-4 border-t border-[#F0F1EC] space-y-1.5 text-sm">
                <p className="text-xs font-semibold text-[#202B28] mb-1.5">Site visits</p>
                {handoff.site_visits.map((v) => (
                  <div key={v.id} className="flex justify-between">
                    <span className="text-[#737C76]">{v.booking_reference}</span>
                    <span className="font-medium text-[#202B28]">
                      {formatDateTime(v.start_time)} · {v.status}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="bg-white rounded-xl border border-[#E5E5DE] shadow-xs p-6 space-y-3">
            <p className="text-xs font-semibold text-[#202B28]">Actions</p>
            <div className="flex flex-col gap-2">
              {isAssignedExecutive && handoff.status === "ASSIGNED" && (
                <>
                  <button
                    disabled={actionPending}
                    onClick={() => runAction(() => apiClient.acceptHandoff(handoff.id).then(() => {}))}
                    className="h-10 px-4 rounded-lg bg-[#173B35] hover:bg-[#1f4b43] text-white text-sm font-semibold disabled:opacity-60"
                  >
                    Accept
                  </button>
                  <button
                    disabled={actionPending}
                    onClick={() => runAction(() => apiClient.rejectHandoff(handoff.id).then(() => {}))}
                    className="h-10 px-4 rounded-lg border border-[#C34D4D] text-[#C34D4D] text-sm font-semibold disabled:opacity-60"
                  >
                    Reject
                  </button>
                </>
              )}

              {(isAssignedExecutive || isManagerOrAdmin) &&
                (handoff.status === "ASSIGNED" || handoff.status === "ACCEPTED") && (
                  <button
                    disabled={actionPending}
                    onClick={() => runAction(() => apiClient.resolveHandoff(handoff.id).then(() => {}))}
                    className="h-10 px-4 rounded-lg border border-[#315C50] text-[#173B35] text-sm font-semibold disabled:opacity-60"
                  >
                    Resolve
                  </button>
                )}

              {isManagerOrAdmin && handoff.status !== "RESOLVED" && handoff.status !== "CANCELLED" && (
                <div className="flex gap-2">
                  <select
                    value={reassignTo}
                    onChange={(e) => setReassignTo(e.target.value)}
                    className="flex-1 h-10 px-3 rounded-lg border border-[#E5E5DE] text-sm bg-white focus:outline-none focus:ring-2 focus:ring-[#315C50]"
                  >
                    <option value="">Reassign to...</option>
                    {executives.map((e) => (
                      <option key={e.id} value={e.id}>
                        {e.full_name}
                      </option>
                    ))}
                  </select>
                  <button
                    disabled={actionPending || !reassignTo}
                    onClick={() => runAction(() => apiClient.reassignHandoff(handoff.id, reassignTo).then(() => {}))}
                    className="h-10 px-4 rounded-lg bg-[#173B35] hover:bg-[#1f4b43] text-white text-sm font-semibold disabled:opacity-60"
                  >
                    Go
                  </button>
                </div>
              )}

              {isManagerOrAdmin && handoff.conversation_ownership_status !== "AI_ACTIVE" && (
                <button
                  disabled={actionPending}
                  onClick={() =>
                    runAction(() => apiClient.transitionOwnership(handoff.conversation_id, "AI_ACTIVE").then(() => {}))
                  }
                  className="h-10 px-4 rounded-lg border border-[#E5E5DE] text-[#202B28] text-sm font-semibold disabled:opacity-60"
                >
                  Return to AI
                </button>
              )}
            </div>
          </div>
        </div>

        <div className="lg:col-span-2 bg-white rounded-xl border border-[#E5E5DE] shadow-xs flex flex-col max-h-[calc(100vh-220px)]">
          <div className="px-6 py-4 border-b border-[#E5E5DE] flex items-center gap-2">
            <UserCheck className="w-4 h-4 text-[#173B35]" />
            <h2 className="text-sm font-semibold text-[#202B28]">Conversation</h2>
            <span className="text-xs text-[#737C76]">({handoff.conversation_ownership_status.replace(/_/g, " ")})</span>
          </div>
          <div className="flex-1 overflow-y-auto px-6 py-4 space-y-3">
            {messages.length === 0 ? (
              <p className="text-sm text-[#737C76]">No messages yet.</p>
            ) : (
              messages.map((message) => {
                const isBuyer = message.sender_type === "BUYER";
                return (
                  <div key={message.id} className={`flex ${isBuyer ? "justify-start" : "justify-end"}`}>
                    <div
                      className={`max-w-[75%] rounded-xl px-3.5 py-2.5 text-sm shadow-xs ${
                        isBuyer
                          ? "bg-[#F0F1EC] text-[#202B28] rounded-bl-sm"
                          : message.sender_type === "STAFF"
                          ? "bg-[#C47A55] text-white rounded-br-sm"
                          : "bg-[#173B35] text-white rounded-br-sm"
                      }`}
                    >
                      <p className="text-[10px] font-semibold uppercase tracking-wide mb-1 opacity-70">
                        {SENDER_LABEL[message.sender_type]}
                      </p>
                      <p className="whitespace-pre-wrap break-words">{message.content}</p>
                      <p className={`text-[10px] mt-1 ${isBuyer ? "text-[#9EA69F]" : "text-white/70"}`}>
                        {new Date(message.created_at).toLocaleString()}
                      </p>
                    </div>
                  </div>
                );
              })
            )}
          </div>
          <div className="px-6 py-4 border-t border-[#E5E5DE] flex items-center gap-2">
            <input
              value={reply}
              onChange={(e) => setReply(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !sending) handleSendReply();
              }}
              disabled={!canReply || sending}
              placeholder={canReply ? "Type your reply..." : "You cannot reply to this conversation right now."}
              className="flex-1 h-10 px-3 rounded-lg border border-[#E5E5DE] text-sm focus:outline-none focus:ring-2 focus:ring-[#315C50] disabled:bg-[#F7F6F2] disabled:text-[#9EA69F]"
            />
            <button
              onClick={handleSendReply}
              disabled={!canReply || sending || !reply.trim()}
              className="h-10 px-4 rounded-lg bg-[#173B35] hover:bg-[#1f4b43] text-white text-sm font-semibold flex items-center gap-2 disabled:opacity-60"
            >
              <Send className="w-4 h-4" />
              Send
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
