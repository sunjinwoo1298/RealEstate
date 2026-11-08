"use client";

import React, { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { Loader2, AlertCircle, CheckCircle2, MailCheck } from "lucide-react";
import { customerApiClient, CustomerApiError } from "@/lib/customer-api-client";

type VerifyState = "VERIFYING" | "SUCCESS" | "ERROR" | "NO_TOKEN";

export default function VerifyEmailPage() {
  return (
    <Suspense fallback={<Loader2 className="w-5 h-5 text-[#173B35] animate-spin" />}>
      <VerifyEmailContent />
    </Suspense>
  );
}

function VerifyEmailContent() {
  const searchParams = useSearchParams();
  const token = searchParams.get("token");

  const [state, setState] = useState<VerifyState>(token ? "VERIFYING" : "NO_TOKEN");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;
    (async () => {
      try {
        await customerApiClient.verifyEmail(token);
        setState("SUCCESS");
      } catch (err) {
        setErrorMessage(
          err instanceof CustomerApiError ? err.message : "This verification link is invalid or has expired."
        );
        setState("ERROR");
      }
    })();
  }, [token]);

  if (state === "VERIFYING") {
    return (
      <div className="w-full max-w-sm text-center">
        <Loader2 className="w-6 h-6 text-[#173B35] animate-spin mx-auto" />
        <p className="text-sm text-[#737C76] mt-4">Verifying your email...</p>
      </div>
    );
  }

  if (state === "SUCCESS") {
    return (
      <div className="w-full max-w-sm text-center">
        <div className="w-14 h-14 rounded-full bg-[#E9F5EF] text-[#27845B] flex items-center justify-center mx-auto">
          <CheckCircle2 className="w-7 h-7" />
        </div>
        <h1 className="font-heading font-bold text-xl text-[#202B28] mt-5">Email verified</h1>
        <p className="text-sm text-[#737C76] mt-3 leading-relaxed">
          Your account is now active. You can sign in to continue.
        </p>
        <Link
          href="/customer/login"
          className="inline-flex items-center justify-center mt-6 h-11 px-5 rounded-lg bg-[#173B35] hover:bg-[#1f4b43] text-white text-sm font-semibold transition-colors"
        >
          Sign in
        </Link>
      </div>
    );
  }

  if (state === "ERROR") {
    return (
      <div className="w-full max-w-sm">
        <div className="text-center mb-6">
          <div className="w-14 h-14 rounded-full bg-[#FDF2F2] text-[#C34D4D] flex items-center justify-center mx-auto">
            <AlertCircle className="w-7 h-7" />
          </div>
          <h1 className="font-heading font-bold text-xl text-[#202B28] mt-5">Verification failed</h1>
          <p className="text-sm text-[#737C76] mt-3 leading-relaxed">{errorMessage}</p>
        </div>
        <ResendVerificationForm />
      </div>
    );
  }

  return (
    <div className="w-full max-w-sm">
      <div className="text-center mb-6">
        <div className="w-14 h-14 rounded-full bg-[#E9F5EF] text-[#27845B] flex items-center justify-center mx-auto">
          <MailCheck className="w-7 h-7" />
        </div>
        <h1 className="font-heading font-bold text-xl text-[#202B28] mt-5">Verify your email</h1>
        <p className="text-sm text-[#737C76] mt-3 leading-relaxed">
          Click the link in the email we sent you, or request a new one below.
        </p>
      </div>
      <ResendVerificationForm />
    </div>
  );
}

function ResendVerificationForm() {
  const [email, setEmail] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const result = await customerApiClient.resendVerification(email);
      setMessage(result.message);
    } catch (err) {
      setError(err instanceof CustomerApiError ? err.message : "Something went wrong. Please try again.");
    } finally {
      setSubmitting(false);
    }
  };

  if (message) {
    return <p className="text-sm text-[#27845B] text-center bg-[#E9F5EF] rounded-lg px-3 py-2.5">{message}</p>;
  }

  return (
    <form onSubmit={handleSubmit} className="bg-white rounded-xl border border-[#E5E5DE] shadow-xs p-6 space-y-4">
      {error && (
        <div className="flex items-start gap-2 text-sm text-[#C34D4D] bg-[#FDF2F2] border border-[#F8D2D2] rounded-lg px-3 py-2.5">
          <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
          <span>{error}</span>
        </div>
      )}
      <div>
        <label htmlFor="resend_email" className="block text-xs font-semibold text-[#202B28] mb-1.5">
          Email
        </label>
        <input
          id="resend_email"
          type="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          className="w-full h-11 px-3 rounded-lg border border-[#E5E5DE] bg-white text-sm text-[#202B28] focus:outline-none focus:ring-2 focus:ring-[#315C50] focus:border-[#315C50] transition-colors"
          placeholder="you@example.com"
        />
      </div>
      <button
        type="submit"
        disabled={submitting}
        className="w-full h-11 rounded-lg bg-[#173B35] hover:bg-[#1f4b43] disabled:opacity-60 disabled:cursor-not-allowed text-white text-sm font-semibold transition-colors flex items-center justify-center gap-2"
      >
        {submitting && <Loader2 className="w-4 h-4 animate-spin" />}
        {submitting ? "Sending..." : "Resend verification email"}
      </button>
    </form>
  );
}
