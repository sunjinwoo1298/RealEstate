"use client";

import React, { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { AlertCircle, Loader2 } from "lucide-react";
import { useCustomerAuth } from "@/lib/customer-auth-context";
import { customerApiClient, CustomerApiError } from "@/lib/customer-api-client";

export default function NewCustomerConversationPage() {
  const { customer, isLoading } = useCustomerAuth();
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  // Guards against the create-conversation request firing twice (e.g. a
  // React fast-refresh remount in dev) -- the user never sees a double click,
  // this just prevents the effect itself from racing.
  const startedRef = useRef(false);

  useEffect(() => {
    if (isLoading) return;
    if (!customer) {
      router.replace("/customer/login?returnTo=/customer/chat/new");
      return;
    }
    if (startedRef.current) return;
    startedRef.current = true;

    (async () => {
      try {
        const conversation = await customerApiClient.createConversation();
        router.replace(`/customer/chat/${conversation.id}`);
      } catch (err) {
        setError(
          err instanceof CustomerApiError
            ? err.message
            : "Unable to start a new conversation. Please try again."
        );
      }
    })();
  }, [isLoading, customer, router]);

  if (error) {
    return (
      <div className="w-full max-w-sm mx-auto">
        <div className="bg-white rounded-xl border border-[#F8D2D2] shadow-xs p-6 text-center">
          <AlertCircle className="w-8 h-8 text-[#C34D4D] mx-auto mb-3" />
          <h2 className="text-lg font-bold font-heading text-[#202B28] mb-1">Couldn&apos;t start a conversation</h2>
          <p className="text-sm text-[#737C76] mb-5">{error}</p>
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

  return (
    <div className="w-full flex justify-center py-16">
      <Loader2 className="w-5 h-5 text-[#173B35] animate-spin" />
    </div>
  );
}
