"use client";

import React, { useEffect, useRef, useState } from "react";
import { Building2, Loader2, AlertCircle, Headset, Send, WifiOff, MessageSquare } from "lucide-react";
import {
  apiClient,
  ApiError,
  ConversationLanguage,
  ConversationPublic,
  MessagePublic,
} from "@/lib/api-client";

const OWNERSHIP_BANNER: Record<string, { text: string; className: string } | undefined> = {
  PENDING_ASSIGNMENT: {
    text: "We're connecting you with a member of our sales team. They'll join this chat shortly.",
    className: "bg-[#FDF6EC] text-[#B9772F] border-[#F3E2C2]",
  },
  HUMAN_ACTIVE: {
    text: "A sales executive has joined this chat.",
    className: "bg-[#E9F5EF] text-[#27845B] border-[#C9E8D8]",
  },
  RESOLVED: {
    text: "This conversation has been resolved by our team.",
    className: "bg-[#F0F1EC] text-[#202B28] border-[#E5E5DE]",
  },
};

type ViewState = "loading" | "entry" | "chat" | "expired";

const LANGUAGE_OPTIONS: { value: ConversationLanguage; label: string }[] = [
  { value: "EN", label: "English" },
  { value: "HI", label: "Hindi" },
  { value: "GU", label: "Gujarati" },
];

export default function BuyerChatPage() {
  const [view, setView] = useState<ViewState>("loading");
  const [conversation, setConversation] = useState<ConversationPublic | null>(null);
  const [messages, setMessages] = useState<MessagePublic[]>([]);
  const [messagesError, setMessagesError] = useState<string | null>(null);
  const [disconnected, setDisconnected] = useState(false);
  const [handoffRequested, setHandoffRequested] = useState(false);

  // Entry form state
  const [fullName, setFullName] = useState("");
  const [phone, setPhone] = useState("");
  const [email, setEmail] = useState("");
  const [language, setLanguage] = useState<ConversationLanguage>("EN");
  const [consent, setConsent] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  // Composer state
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const [aiTyping, setAiTyping] = useState(false);
  const scrollRef = useRef<HTMLDivElement | null>(null);

  const loadMessages = async (conversationId: string) => {
    try {
      const data = await apiClient.getChatMessages(conversationId, { limit: 100 });
      setMessages(data.items);
      setMessagesError(null);
      setDisconnected(false);
      // Ownership can change server-side (AI escalation, an executive
      // joining/resolving) independently of anything the buyer just sent,
      // so re-fetch the conversation alongside messages to keep the banner
      // in sync rather than only reflecting ownership as of chat start.
      const refreshed = await apiClient.getChatConversation(conversationId);
      setConversation(refreshed);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        setView("expired");
        return;
      }
      setDisconnected(true);
      setMessagesError(err instanceof ApiError ? err.message : "Unable to reach the server.");
    }
  };

  // Session recovery on load/reload.
  useEffect(() => {
    (async () => {
      try {
        const existing = await apiClient.getChatSession();
        setConversation(existing);
        setView("chat");
        await loadMessages(existing.id);
      } catch {
        setView("entry");
      }
    })();
  }, []);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages]);

  const handleStartChat = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError(null);
    if (!consent) {
      setFormError("Please accept to be contacted before starting a chat.");
      return;
    }
    setSubmitting(true);
    try {
      const created = await apiClient.createChatSession({
        full_name: fullName,
        phone,
        email: email || undefined,
        preferred_language: language,
        consent_given: consent,
      });
      setConversation(created);
      setView("chat");
      await loadMessages(created.id);
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : "Unable to start chat. Please try again.");
    } finally {
      setSubmitting(false);
    }
  };

  const handleSend = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!conversation || !draft.trim()) return;
    setSending(true);
    const content = draft.trim();
    try {
      // The backend generates the AI reply synchronously as part of this
      // request, so "typing" reflects real processing time, not padding.
      setAiTyping(true);
      const sent = await apiClient.sendChatMessage(conversation.id, content);
      setMessages((prev) => [...prev, sent]);
      setDraft("");
      setDisconnected(false);
      setMessagesError(null);
      await loadMessages(conversation.id);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        setView("expired");
        return;
      }
      setDisconnected(true);
      setMessagesError(err instanceof ApiError ? err.message : "Failed to send message.");
    } finally {
      setSending(false);
      setAiTyping(false);
    }
  };

  const handleRequestHandoff = async () => {
    if (!conversation) return;
    setHandoffRequested(true);
    try {
      await apiClient.requestHandoff(conversation.id);
      await loadMessages(conversation.id);
    } catch (err) {
      setMessagesError(err instanceof ApiError ? err.message : "Failed to request a sales executive.");
      setHandoffRequested(false);
    }
  };

  const handleStartOver = () => {
    setConversation(null);
    setMessages([]);
    setFullName("");
    setPhone("");
    setEmail("");
    setConsent(false);
    setView("entry");
  };

  if (view === "loading") {
    return (
      <div className="h-screen w-screen flex items-center justify-center bg-[#F7F6F2]">
        <Loader2 className="w-5 h-5 text-[#173B35] animate-spin" />
      </div>
    );
  }

  if (view === "expired") {
    return (
      <div className="min-h-screen w-full flex items-center justify-center bg-[#F7F6F2] px-4">
        <div className="w-full max-w-sm bg-white rounded-xl border border-[#E5E5DE] shadow-xs p-6 text-center">
          <AlertCircle className="w-8 h-8 text-[#B7791F] mx-auto mb-3" />
          <h2 className="text-lg font-bold font-heading text-[#202B28] mb-1">Session expired</h2>
          <p className="text-sm text-[#737C76] mb-5">
            Your chat session has ended. Start a new conversation to continue.
          </p>
          <button
            onClick={handleStartOver}
            className="w-full h-11 rounded-lg bg-[#173B35] hover:bg-[#1f4b43] text-white text-sm font-semibold transition-colors"
          >
            Start a new chat
          </button>
        </div>
      </div>
    );
  }

  if (view === "entry") {
    return (
      <div className="min-h-screen w-full flex items-center justify-center bg-[#F7F6F2] px-4 py-8">
        <div className="w-full max-w-sm">
          <div className="flex flex-col items-center mb-6">
            <div className="w-12 h-12 rounded-xl bg-[#C47A55] flex items-center justify-center shadow-sm mb-4">
              <Building2 className="w-6 h-6 text-white" />
            </div>
            <h1 className="font-heading font-bold text-xl text-[#202B28] tracking-tight">
              EstateFlow <span className="text-[#C47A55]">AI</span>
            </h1>
            <p className="text-xs text-[#737C76] mt-1 tracking-wide uppercase font-medium">Chat with us</p>
          </div>

          <div className="bg-white rounded-xl border border-[#E5E5DE] shadow-xs p-6">
            <h2 className="text-lg font-bold font-heading text-[#202B28] mb-1">Start a conversation</h2>
            <p className="text-sm text-[#737C76] mb-5">
              Tell us a bit about yourself so we can help you find the right home.
            </p>

            {formError && (
              <div className="mb-4 flex items-start gap-2 text-sm text-[#C34D4D] bg-[#FDF2F2] border border-[#F8D2D2] rounded-lg px-3 py-2.5">
                <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
                <span>{formError}</span>
              </div>
            )}

            <form onSubmit={handleStartChat} className="space-y-4">
              <div>
                <label className="block text-xs font-semibold text-[#202B28] mb-1.5">Full name</label>
                <input
                  required
                  value={fullName}
                  onChange={(e) => setFullName(e.target.value)}
                  className="w-full h-11 px-3 rounded-lg border border-[#E5E5DE] bg-white text-sm text-[#202B28] focus:outline-none focus:ring-2 focus:ring-[#315C50] focus:border-[#315C50] transition-colors"
                  placeholder="Your name"
                />
              </div>
              <div>
                <label className="block text-xs font-semibold text-[#202B28] mb-1.5">Phone number</label>
                <input
                  required
                  value={phone}
                  onChange={(e) => setPhone(e.target.value)}
                  className="w-full h-11 px-3 rounded-lg border border-[#E5E5DE] bg-white text-sm text-[#202B28] focus:outline-none focus:ring-2 focus:ring-[#315C50] focus:border-[#315C50] transition-colors"
                  placeholder="9876543210"
                />
              </div>
              <div>
                <label className="block text-xs font-semibold text-[#202B28] mb-1.5">Email (optional)</label>
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="w-full h-11 px-3 rounded-lg border border-[#E5E5DE] bg-white text-sm text-[#202B28] focus:outline-none focus:ring-2 focus:ring-[#315C50] focus:border-[#315C50] transition-colors"
                  placeholder="you@example.com"
                />
              </div>
              <div>
                <label className="block text-xs font-semibold text-[#202B28] mb-1.5">Preferred language</label>
                <select
                  value={language}
                  onChange={(e) => setLanguage(e.target.value as ConversationLanguage)}
                  className="w-full h-11 px-3 rounded-lg border border-[#E5E5DE] bg-white text-sm text-[#202B28] focus:outline-none focus:ring-2 focus:ring-[#315C50]"
                >
                  {LANGUAGE_OPTIONS.map((opt) => (
                    <option key={opt.value} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </select>
              </div>
              <label className="flex items-start gap-2.5 text-xs text-[#737C76] cursor-pointer">
                <input
                  type="checkbox"
                  checked={consent}
                  onChange={(e) => setConsent(e.target.checked)}
                  className="mt-0.5 w-4 h-4 rounded border-[#E5E5DE] text-[#173B35] focus:ring-[#315C50]"
                />
                <span>
                  I agree to be contacted by EstateFlow AI and its sales team about my enquiry via chat, call or
                  WhatsApp.
                </span>
              </label>

              <button
                type="submit"
                disabled={submitting}
                className="w-full h-11 rounded-lg bg-[#173B35] hover:bg-[#1f4b43] disabled:opacity-60 disabled:cursor-not-allowed text-white text-sm font-semibold transition-colors flex items-center justify-center gap-2"
              >
                {submitting && <Loader2 className="w-4 h-4 animate-spin" />}
                {submitting ? "Starting..." : "Start chat"}
              </button>
            </form>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="h-screen w-full flex flex-col bg-[#F7F6F2]">
      <header className="h-16 bg-white border-b border-[#E5E5DE] px-4 flex items-center gap-3 shrink-0">
        <div className="w-9 h-9 rounded-lg bg-[#C47A55] flex items-center justify-center shrink-0">
          <Building2 className="w-5 h-5 text-white" />
        </div>
        <div className="flex-1 min-w-0">
          <p className="font-heading font-bold text-sm text-[#202B28] truncate">EstateFlow AI</p>
          <p className="text-[11px] text-[#737C76]">
            {disconnected ? (
              <span className="flex items-center gap-1 text-[#C34D4D]">
                <WifiOff className="w-3 h-3" /> Disconnected
              </span>
            ) : (
              "We usually reply within a few minutes"
            )}
          </p>
        </div>
        {conversation?.ownership_status === "AI_ACTIVE" && (
          <button
            onClick={handleRequestHandoff}
            disabled={handoffRequested}
            className="h-9 px-3 rounded-lg border border-[#315C50] text-[#173B35] text-xs font-semibold flex items-center gap-1.5 hover:bg-[#E9F5EF] disabled:opacity-60 transition-colors shrink-0"
          >
            <Headset className="w-3.5 h-3.5" />
            Talk to a human
          </button>
        )}
      </header>

      {conversation && OWNERSHIP_BANNER[conversation.ownership_status] && (
        <div
          className={`mx-4 mt-3 flex items-center gap-2 text-xs rounded-lg border px-3 py-2 shrink-0 ${
            OWNERSHIP_BANNER[conversation.ownership_status]!.className
          }`}
        >
          <Headset className="w-3.5 h-3.5 shrink-0" />
          <span>{OWNERSHIP_BANNER[conversation.ownership_status]!.text}</span>
        </div>
      )}

      <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 py-6 space-y-3">
        {messages.length === 0 && !messagesError ? (
          <div className="h-full flex flex-col items-center justify-center text-center text-[#737C76]">
            <MessageSquare className="w-8 h-8 text-[#C5C5BB] mb-3" />
            <p className="text-sm">Say hello to get started. Our team is here to help.</p>
          </div>
        ) : (
          messages.map((message) => {
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
                      : "bg-white border border-[#E5E5DE] text-[#202B28] rounded-bl-sm"
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
            <div className="bg-white border border-[#E5E5DE] rounded-xl rounded-bl-sm px-3.5 py-2.5 shadow-xs flex items-center gap-1.5">
              <span className="w-1.5 h-1.5 rounded-full bg-[#C5C5BB] animate-bounce [animation-delay:-0.3s]" />
              <span className="w-1.5 h-1.5 rounded-full bg-[#C5C5BB] animate-bounce [animation-delay:-0.15s]" />
              <span className="w-1.5 h-1.5 rounded-full bg-[#C5C5BB] animate-bounce" />
            </div>
          </div>
        )}
        {messagesError && (
          <div className="flex items-center gap-2 text-xs text-[#C34D4D] bg-[#FDF2F2] border border-[#F8D2D2] rounded-lg px-3 py-2">
            <AlertCircle className="w-3.5 h-3.5 shrink-0" />
            <span>{messagesError}</span>
          </div>
        )}
      </div>

      <form onSubmit={handleSend} className="border-t border-[#E5E5DE] bg-white p-3 flex items-end gap-2 shrink-0">
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
          placeholder="Type your message..."
          className="flex-1 resize-none max-h-32 px-3.5 py-2.5 rounded-lg border border-[#E5E5DE] text-sm text-[#202B28] focus:outline-none focus:ring-2 focus:ring-[#315C50] focus:border-[#315C50] transition-colors"
        />
        <button
          type="submit"
          disabled={sending || !draft.trim()}
          className="h-10 w-10 shrink-0 rounded-lg bg-[#173B35] hover:bg-[#1f4b43] disabled:opacity-40 text-white flex items-center justify-center transition-colors"
          aria-label="Send message"
        >
          {sending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
        </button>
      </form>
    </div>
  );
}
