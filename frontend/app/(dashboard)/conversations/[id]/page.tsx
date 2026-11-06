"use client";

import React, { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { ArrowLeft, Loader2, Phone, Globe } from "lucide-react";
import { apiClient, ApiError, ConversationListItem, MessagePublic } from "@/lib/api-client";

const SENDER_LABEL: Record<string, string> = {
  BUYER: "Buyer",
  AI: "AI",
  STAFF: "Staff",
  SYSTEM: "System",
};

export default function ConversationDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();

  const [conversation, setConversation] = useState<ConversationListItem | null>(null);
  const [messages, setMessages] = useState<MessagePublic[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      setLoading(true);
      try {
        const [conversationData, messagesData] = await Promise.all([
          apiClient.getConversation(params.id),
          apiClient.getConversationMessages(params.id, { limit: 100 }),
        ]);
        setConversation(conversationData);
        setMessages(messagesData.items);
        setError(null);
      } catch (err) {
        setError(err instanceof ApiError ? err.message : "Failed to load conversation.");
      } finally {
        setLoading(false);
      }
    })();
  }, [params.id]);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20 text-sm text-[#737C76] gap-2">
        <Loader2 className="w-4 h-4 animate-spin" />
        Loading conversation...
      </div>
    );
  }

  if (error || !conversation) {
    return <p className="text-sm text-[#C34D4D]">{error || "Conversation not found."}</p>;
  }

  return (
    <div className="space-y-6">
      <button
        onClick={() => router.push("/conversations")}
        className="flex items-center gap-1.5 text-sm text-[#737C76] hover:text-[#202B28] transition-colors"
      >
        <ArrowLeft className="w-4 h-4" />
        Back to conversations
      </button>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-1 bg-white rounded-xl border border-[#E5E5DE] shadow-xs p-6 space-y-4">
          <div>
            <h1 className="text-lg font-bold font-heading text-[#202B28]">{conversation.lead_full_name}</h1>
            <span className="text-xs font-semibold px-2 py-1 rounded-md bg-[#E9F5EF] text-[#27845B] inline-block mt-2">
              {conversation.status}
            </span>
          </div>
          <div className="space-y-2 text-sm text-[#737C76]">
            {conversation.lead_normalized_phone && (
              <div className="flex items-center gap-2">
                <Phone className="w-4 h-4 text-[#9EA69F]" />
                {conversation.lead_normalized_phone}
              </div>
            )}
            <div className="flex items-center gap-2">
              <Globe className="w-4 h-4 text-[#9EA69F]" />
              {conversation.language}
            </div>
          </div>
          <div className="pt-4 border-t border-[#F0F1EC] space-y-2 text-sm">
            <div className="flex justify-between">
              <span className="text-[#737C76]">Conversation state</span>
              <span className="font-medium text-[#202B28]">{conversation.conversation_state.replace(/_/g, " ")}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-[#737C76]">Ownership</span>
              <span className="font-medium text-[#202B28]">{conversation.ownership_status.replace(/_/g, " ")}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-[#737C76]">Created</span>
              <span className="font-medium text-[#202B28]">{new Date(conversation.created_at).toLocaleString()}</span>
            </div>
          </div>
        </div>

        <div className="lg:col-span-2 bg-white rounded-xl border border-[#E5E5DE] shadow-xs flex flex-col max-h-[calc(100vh-220px)]">
          <div className="px-6 py-4 border-b border-[#E5E5DE]">
            <h2 className="text-sm font-semibold text-[#202B28]">Message history</h2>
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
                          : "bg-[#173B35] text-white rounded-br-sm"
                      }`}
                    >
                      <p className="text-[10px] font-semibold uppercase tracking-wide mb-1 opacity-70">
                        {SENDER_LABEL[message.sender_type]}
                      </p>
                      <p className="whitespace-pre-wrap break-words">{message.content}</p>
                      <p className={`text-[10px] mt-1 ${isBuyer ? "text-[#9EA69F]" : "text-[#A3B8B0]"}`}>
                        {new Date(message.created_at).toLocaleString()}
                      </p>
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
