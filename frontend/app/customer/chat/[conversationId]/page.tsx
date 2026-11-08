"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { AlertCircle, ArrowLeft, Headset, Loader2, MessageSquare, Send } from "lucide-react";
import { useCustomerAuth } from "@/lib/customer-auth-context";
import {
  customerApiClient,
  CustomerApiError,
  CustomerChatMessage,
  CustomerConversation,
} from "@/lib/customer-api-client";
import { OWNERSHIP_BADGE_CLASS, OWNERSHIP_LABEL } from "@/lib/customer-chat-constants";

const SUGGESTED_QUESTIONS = [
  "Tell me about the available 2 BHK and 3 BHK configurations.",
  "What amenities are available in this project?",
  "Can someone from the sales team contact me?",
  "I would like to discuss my property requirements.",
];

export default function CustomerConversationPage() {
  const { customer, isLoading } = useCustomerAuth();
  const router = useRouter();
  const params = useParams<{ conversationId: string }>();
  const conversationId = params.conversationId;

  const [conversation, setConversation] = useState<CustomerConversation | null>(null);
  const [messages, setMessages] = useState<CustomerChatMessage[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [notFound, setNotFound] = useState(false);
  const [loadingInitial, setLoadingInitial] = useState(true);

  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const [aiTyping, setAiTyping] = useState(false);
  const [handoffRequesting, setHandoffRequesting] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const scrollRef = useRef<HTMLDivElement | null>(null);
  // Guards against a slow, superseded refresh overwriting state from a
  // later request (e.g. a background poll resolving after a send).
  const requestSeqRef = useRef(0);

  useEffect(() => {
    if (!isLoading && !customer) {
      router.replace(`/customer/login?returnTo=/customer/chat/${conversationId}`);
    }
  }, [isLoading, customer, router, conversationId]);

  const refresh = useCallback(async () => {
    const seq = ++requestSeqRef.current;
    try {
      const [conversationResult, messagesResult] = await Promise.all([
        customerApiClient.getConversation(conversationId),
        customerApiClient.getConversationMessages(conversationId, { limit: 100 }),
      ]);
      if (seq !== requestSeqRef.current) return;
      setConversation(conversationResult);
      setMessages(messagesResult.items);
      setLoadError(null);
      setNotFound(false);
    } catch (err) {
      if (seq !== requestSeqRef.current) return;
      if (err instanceof CustomerApiError && err.status === 404) {
        setNotFound(true);
        return;
      }
      setLoadError(err instanceof CustomerApiError ? err.message : "Unable to reach the server.");
    }
  }, [conversationId]);

  useEffect(() => {
    if (!customer) return;
    (async () => {
      setLoadingInitial(true);
      await refresh();
      setLoadingInitial(false);
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- refresh is stable across conversationId via useCallback
  }, [customer, conversationId]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages]);

  const handleSend = async (e: React.FormEvent, presetContent?: string) => {
    e.preventDefault();
    const content = (presetContent ?? draft).trim();
    if (!content || sending) return;

    setSending(true);
    setActionError(null);
    try {
      setAiTyping(conversation?.ownership_status === "AI_ACTIVE");
      await customerApiClient.sendConversationMessage(conversationId, content);
      setDraft("");
      await refresh();
    } catch (err) {
      setActionError(err instanceof CustomerApiError ? err.message : "Failed to send your message.");
    } finally {
      setSending(false);
      setAiTyping(false);
    }
  };

  const handleRequestHandoff = async () => {
    setHandoffRequesting(true);
    setActionError(null);
    try {
      await customerApiClient.requestConversationHandoff(conversationId);
      await refresh();
    } catch (err) {
      setActionError(err instanceof CustomerApiError ? err.message : "Failed to request a sales executive.");
    } finally {
      setHandoffRequesting(false);
    }
  };

  if (isLoading || !customer || loadingInitial) {
    return (
      <div className="w-full flex justify-center py-16">
        <Loader2 className="w-5 h-5 text-[#173B35] animate-spin" />
      </div>
    );
  }

  if (notFound) {
    return (
      <div className="w-full max-w-sm mx-auto">
        <div className="bg-white rounded-xl border border-[#E5E5DE] shadow-xs p-6 text-center">
          <AlertCircle className="w-8 h-8 text-[#B7791F] mx-auto mb-3" />
          <h2 className="text-lg font-bold font-heading text-[#202B28] mb-1">Conversation not found</h2>
          <p className="text-sm text-[#737C76] mb-5">
            This conversation doesn&apos;t exist or isn&apos;t associated with your account.
          </p>
          <Link
            href="/customer/chat"
            className="inline-block h-10 px-4 rounded-lg bg-[#173B35] hover:bg-[#1f4b43] text-white text-sm font-semibold transition-colors"
          >
            Back to conversations
          </Link>
        </div>
      </div>
    );
  }

  const resolved = conversation?.ownership_status === "RESOLVED";
  const composerDisabled = sending || resolved;

  return (
    <div className="w-full max-w-2xl flex flex-col h-[78vh] bg-white rounded-xl border border-[#E5E5DE] shadow-xs overflow-hidden">
      <header className="shrink-0 border-b border-[#E5E5DE] px-4 py-3 flex items-center gap-3">
        <Link href="/customer/chat" className="text-[#737C76] hover:text-[#202B28] transition-colors shrink-0">
          <ArrowLeft className="w-4 h-4" />
        </Link>
        <div className="flex-1 min-w-0">
          <p className="font-heading font-bold text-sm text-[#202B28]">EstateFlow AI</p>
          {conversation && (
            <span
              className={`inline-block text-[11px] font-semibold px-2 py-0.5 rounded-full mt-0.5 ${
                OWNERSHIP_BADGE_CLASS[conversation.ownership_status] || "bg-[#F0F1EC] text-[#737C76]"
              }`}
            >
              {OWNERSHIP_LABEL[conversation.ownership_status] || conversation.ownership_status}
            </span>
          )}
        </div>
        {conversation?.ownership_status === "AI_ACTIVE" && (
          <button
            onClick={handleRequestHandoff}
            disabled={handoffRequesting}
            className="h-9 px-3 rounded-lg border border-[#315C50] text-[#173B35] text-xs font-semibold flex items-center gap-1.5 hover:bg-[#E9F5EF] disabled:opacity-60 transition-colors shrink-0"
          >
            <Headset className="w-3.5 h-3.5" />
            Talk to a salesperson
          </button>
        )}
      </header>

      <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 py-5 space-y-3">
        {loadError && (
          <div className="flex items-center gap-2 text-xs text-[#C34D4D] bg-[#FDF2F2] border border-[#F8D2D2] rounded-lg px-3 py-2 mb-2">
            <AlertCircle className="w-3.5 h-3.5 shrink-0" />
            <span>{loadError}</span>
            <button onClick={refresh} className="ml-auto font-semibold underline shrink-0">
              Retry
            </button>
          </div>
        )}

        {messages && messages.length === 0 && !loadError ? (
          <div className="h-full flex flex-col items-center justify-center text-center text-[#737C76] gap-4">
            <div>
              <MessageSquare className="w-8 h-8 text-[#C5C5BB] mb-3 mx-auto" />
              <p className="text-sm">Ask about a project, or say hello to get started.</p>
            </div>
            <div className="w-full max-w-sm space-y-2">
              {SUGGESTED_QUESTIONS.map((question) => (
                <button
                  key={question}
                  onClick={(e) => handleSend(e, question)}
                  disabled={composerDisabled}
                  className="w-full text-left text-xs px-3 py-2.5 rounded-lg border border-[#E5E5DE] bg-[#F7F6F2] hover:bg-[#F0F1EC] text-[#202B28] transition-colors disabled:opacity-60"
                >
                  {question}
                </button>
              ))}
            </div>
          </div>
        ) : (
          messages?.map((message) => {
            const isBuyer = message.sender_type === "BUYER";
            const isStaff = message.sender_type === "STAFF";
            return (
              <div key={message.id} className={`flex ${isBuyer ? "justify-end" : "justify-start"}`}>
                <div
                  className={`max-w-[80%] rounded-xl px-3.5 py-2.5 text-sm shadow-xs ${
                    isBuyer
                      ? "bg-[#173B35] text-white rounded-br-sm"
                      : isStaff
                      ? "bg-[#C47A55] text-white rounded-bl-sm"
                      : "bg-[#F7F6F2] border border-[#E5E5DE] text-[#202B28] rounded-bl-sm"
                  }`}
                >
                  {isStaff && (
                    <p className="text-[10px] font-semibold uppercase tracking-wide mb-1 opacity-80">Our team</p>
                  )}
                  <p className="whitespace-pre-wrap break-words">{message.content}</p>
                  <p className={`text-[10px] mt-1 ${isBuyer || isStaff ? "text-white/70" : "text-[#9EA69F]"}`}>
                    {new Date(message.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                  </p>
                </div>
              </div>
            );
          })
        )}

        {aiTyping && (
          <div className="flex justify-start">
            <div className="bg-[#F7F6F2] border border-[#E5E5DE] rounded-xl rounded-bl-sm px-3.5 py-2.5 shadow-xs flex items-center gap-1.5">
              <span className="w-1.5 h-1.5 rounded-full bg-[#C5C5BB] animate-bounce [animation-delay:-0.3s]" />
              <span className="w-1.5 h-1.5 rounded-full bg-[#C5C5BB] animate-bounce [animation-delay:-0.15s]" />
              <span className="w-1.5 h-1.5 rounded-full bg-[#C5C5BB] animate-bounce" />
            </div>
          </div>
        )}

        {actionError && (
          <div className="flex items-center gap-2 text-xs text-[#C34D4D] bg-[#FDF2F2] border border-[#F8D2D2] rounded-lg px-3 py-2">
            <AlertCircle className="w-3.5 h-3.5 shrink-0" />
            <span>{actionError}</span>
          </div>
        )}
      </div>

      <form onSubmit={handleSend} className="shrink-0 border-t border-[#E5E5DE] bg-white p-3 flex items-end gap-2">
        <textarea
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              handleSend(e);
            }
          }}
          rows={1}
          disabled={composerDisabled}
          placeholder={resolved ? "This conversation has been resolved." : "Type your message..."}
          className="flex-1 resize-none max-h-32 px-3.5 py-2.5 rounded-lg border border-[#E5E5DE] text-sm text-[#202B28] focus:outline-none focus:ring-2 focus:ring-[#315C50] focus:border-[#315C50] transition-colors disabled:bg-[#F7F6F2] disabled:cursor-not-allowed"
        />
        <button
          type="submit"
          disabled={composerDisabled || !draft.trim()}
          className="h-10 w-10 shrink-0 rounded-lg bg-[#173B35] hover:bg-[#1f4b43] disabled:opacity-40 text-white flex items-center justify-center transition-colors"
          aria-label="Send message"
        >
          {sending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
        </button>
      </form>
    </div>
  );
}
