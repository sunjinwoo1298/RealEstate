"use client";

import React, { useState } from "react";
import Link from "next/link";
import { Loader2, AlertCircle, MailCheck } from "lucide-react";
import { customerApiClient, CustomerApiError } from "@/lib/customer-api-client";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const result = await customerApiClient.forgotPassword(email);
      setMessage(result.message);
    } catch (err) {
      setError(err instanceof CustomerApiError ? err.message : "Something went wrong. Please try again.");
    } finally {
      setSubmitting(false);
    }
  };

  if (message) {
    return (
      <div className="w-full max-w-sm text-center">
        <div className="w-14 h-14 rounded-full bg-[#E9F5EF] text-[#27845B] flex items-center justify-center mx-auto">
          <MailCheck className="w-7 h-7" />
        </div>
        <h1 className="font-heading font-bold text-xl text-[#202B28] mt-5">Check your email</h1>
        <p className="text-sm text-[#737C76] mt-3 leading-relaxed">{message}</p>
        <Link
          href="/customer/login"
          className="inline-flex items-center justify-center mt-6 h-11 px-5 rounded-lg bg-[#173B35] hover:bg-[#1f4b43] text-white text-sm font-semibold transition-colors"
        >
          Back to sign in
        </Link>
      </div>
    );
  }

  return (
    <div className="w-full max-w-sm">
      <div className="bg-white rounded-xl border border-[#E5E5DE] shadow-xs p-6">
        <h2 className="text-lg font-bold font-heading text-[#202B28] mb-1">Forgot your password?</h2>
        <p className="text-sm text-[#737C76] mb-5">
          Enter your email and we&apos;ll send you a link to reset it.
        </p>

        {error && (
          <div className="mb-4 flex items-start gap-2 text-sm text-[#C34D4D] bg-[#FDF2F2] border border-[#F8D2D2] rounded-lg px-3 py-2.5">
            <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label htmlFor="email" className="block text-xs font-semibold text-[#202B28] mb-1.5">
              Email
            </label>
            <input
              id="email"
              type="email"
              required
              autoComplete="email"
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
            {submitting ? "Sending..." : "Send reset link"}
          </button>
        </form>
      </div>

      <p className="text-center text-xs text-[#737C76] mt-6">
        <Link href="/customer/login" className="text-[#173B35] font-semibold hover:underline">
          Back to sign in
        </Link>
      </p>
    </div>
  );
}
