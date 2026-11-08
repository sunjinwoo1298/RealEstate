"use client";

import React, { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { AlertCircle, Loader2, MessageSquare, Plus } from "lucide-react";
import { useCustomerAuth } from "@/lib/customer-auth-context";
import { customerApiClient, CustomerApiError, CustomerConversationListItem } from "@/lib/customer-api-client";
import { OWNERSHIP_BADGE_CLASS, OWNERSHIP_LABEL } from "@/lib/customer-chat-constants";

export default function CustomerChatInboxPage() {
  const { customer, isLoading } = useCustomerAuth();
  const router = useRouter();

  const [conversations, setConversations] = useState<CustomerConversationListItem[] | null>(null);
  const [loadingData, setLoadingData] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!isLoading && !customer) {
      router.replace("/customer/login?returnTo=/customer/chat");
    }
  }, [isLoading, customer, router]);

  const loadConversations = useCallback(async () => {
    setLoadingData(true);
    setError(null);
    try {
      const result = await customerApiClient.listConversations({ limit: 50 });
      setConversations(result.items);
    } catch (err) {
      setError(err instanceof CustomerApiError ? err.message : "Unable to load your conversations. Please try again.");
    } finally {
      setLoadingData(false);
    }
  }, []);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- intentional data fetch on customer load
    if (customer) loadConversations();
  }, [customer, loadConversations]);

  if (isLoading || !customer) {
    return (
      <div className="w-full flex justify-center py-16">
        <Loader2 className="w-5 h-5 text-[#173B35] animate-spin" />
      </div>
    );
  }

  return (
    <div className="w-full max-w-3xl space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-heading font-bold text-xl text-[#202B28]">Chat with us</h1>
          <p className="text-sm text-[#737C76] mt-1">
            Ask our AI assistant about projects, or talk to a sales representative.
          </p>
        </div>
        <Link
          href="/customer/chat/new"
          className="h-10 px-4 rounded-lg bg-[#173B35] hover:bg-[#1f4b43] text-white text-sm font-semibold transition-colors flex items-center gap-1.5 shrink-0"
        >
          <Plus className="w-4 h-4" />
          New conversation
        </Link>
      </div>

      {loadingData && (
        <div className="flex justify-center py-10">
          <Loader2 className="w-5 h-5 text-[#173B35] animate-spin" />
        </div>
      )}

      {!loadingData && error && (
        <div className="bg-white rounded-xl border border-[#F8D2D2] shadow-xs p-6 flex items-start gap-2 text-sm text-[#C34D4D]">
          <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
          <div>
            <p>{error}</p>
            <button onClick={loadConversations} className="mt-2 text-xs font-semibold underline">
              Retry
            </button>
          </div>
        </div>
      )}

      {!loadingData && !error && conversations && conversations.length === 0 && (
        <div className="bg-white rounded-xl border border-[#E5E5DE] shadow-xs p-10 flex flex-col items-center text-center">
          <MessageSquare className="w-8 h-8 text-[#C5C5BB] mb-3" />
          <p className="text-sm text-[#737C76] mb-4">
            You haven&apos;t started a conversation yet. Our AI assistant can help you explore projects and answer
            your questions.
          </p>
          <Link
            href="/customer/chat/new"
            className="h-10 px-4 rounded-lg bg-[#173B35] hover:bg-[#1f4b43] text-white text-sm font-semibold transition-colors inline-flex items-center gap-1.5"
          >
            <Plus className="w-4 h-4" />
            Start a conversation
          </Link>
        </div>
      )}

      {!loadingData && !error && conversations && conversations.length > 0 && (
        <div className="bg-white rounded-xl border border-[#E5E5DE] shadow-xs divide-y divide-[#E5E5DE] overflow-hidden">
          {conversations.map((conversation) => (
            <Link
              key={conversation.id}
              href={`/customer/chat/${conversation.id}`}
              className="flex items-center justify-between gap-4 p-4 hover:bg-[#F7F6F2] transition-colors"
            >
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2 mb-1">
                  <span
                    className={`text-[11px] font-semibold px-2 py-0.5 rounded-full ${
                      OWNERSHIP_BADGE_CLASS[conversation.ownership_status] || "bg-[#F0F1EC] text-[#737C76]"
                    }`}
                  >
                    {OWNERSHIP_LABEL[conversation.ownership_status] || conversation.ownership_status}
                  </span>
                </div>
                <p className="text-sm text-[#202B28] truncate">
                  {conversation.last_message_preview || "No messages yet. Say hello to get started."}
                </p>
              </div>
              <span className="text-xs text-[#9EA69F] shrink-0">
                {new Date(conversation.updated_at).toLocaleDateString()}
              </span>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
