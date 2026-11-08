"use client";

import React, { Suspense, useState } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { Loader2, AlertCircle, CheckCircle2 } from "lucide-react";
import { customerApiClient, CustomerApiError } from "@/lib/customer-api-client";

const PASSWORD_HINT = "At least 8 characters, including one letter and one number.";

export default function ResetPasswordPage() {
  return (
    <Suspense fallback={<Loader2 className="w-5 h-5 text-[#173B35] animate-spin" />}>
      <ResetPasswordForm />
    </Suspense>
  );
}

function ResetPasswordForm() {
  const searchParams = useSearchParams();
  const token = searchParams.get("token");

  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  if (!token) {
    return (
      <div className="w-full max-w-sm text-center">
        <div className="w-14 h-14 rounded-full bg-[#FDF2F2] text-[#C34D4D] flex items-center justify-center mx-auto">
          <AlertCircle className="w-7 h-7" />
        </div>
        <h1 className="font-heading font-bold text-xl text-[#202B28] mt-5">Invalid link</h1>
        <p className="text-sm text-[#737C76] mt-3 leading-relaxed">
          This password reset link is missing its token. Please request a new one.
        </p>
        <Link
          href="/customer/forgot-password"
          className="inline-flex items-center justify-center mt-6 h-11 px-5 rounded-lg bg-[#173B35] hover:bg-[#1f4b43] text-white text-sm font-semibold transition-colors"
        >
          Request a new link
        </Link>
      </div>
    );
  }

  if (success) {
    return (
      <div className="w-full max-w-sm text-center">
        <div className="w-14 h-14 rounded-full bg-[#E9F5EF] text-[#27845B] flex items-center justify-center mx-auto">
          <CheckCircle2 className="w-7 h-7" />
        </div>
        <h1 className="font-heading font-bold text-xl text-[#202B28] mt-5">Password reset</h1>
        <p className="text-sm text-[#737C76] mt-3 leading-relaxed">
          Your password has been reset. You can now sign in with your new password.
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

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (newPassword !== confirmPassword) {
      setError("Password and confirmation do not match.");
      return;
    }

    setSubmitting(true);
    try {
      await customerApiClient.resetPassword(token, newPassword, confirmPassword);
      setSuccess(true);
    } catch (err) {
      setError(
        err instanceof CustomerApiError
          ? err.message
          : "This link may be invalid or expired. Please request a new one."
      );
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="w-full max-w-sm">
      <div className="bg-white rounded-xl border border-[#E5E5DE] shadow-xs p-6">
        <h2 className="text-lg font-bold font-heading text-[#202B28] mb-1">Reset your password</h2>
        <p className="text-sm text-[#737C76] mb-5">Choose a new password for your account.</p>

        {error && (
          <div className="mb-4 flex items-start gap-2 text-sm text-[#C34D4D] bg-[#FDF2F2] border border-[#F8D2D2] rounded-lg px-3 py-2.5">
            <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label htmlFor="new_password" className="block text-xs font-semibold text-[#202B28] mb-1.5">
              New password
            </label>
            <input
              id="new_password"
              type="password"
              required
              minLength={8}
              autoComplete="new-password"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              className="w-full h-11 px-3 rounded-lg border border-[#E5E5DE] bg-white text-sm text-[#202B28] focus:outline-none focus:ring-2 focus:ring-[#315C50] focus:border-[#315C50] transition-colors"
              placeholder="••••••••"
            />
            <p className="text-xs text-[#A3AAA5] mt-1">{PASSWORD_HINT}</p>
          </div>
          <div>
            <label htmlFor="confirm_password" className="block text-xs font-semibold text-[#202B28] mb-1.5">
              Confirm new password
            </label>
            <input
              id="confirm_password"
              type="password"
              required
              minLength={8}
              autoComplete="new-password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              className="w-full h-11 px-3 rounded-lg border border-[#E5E5DE] bg-white text-sm text-[#202B28] focus:outline-none focus:ring-2 focus:ring-[#315C50] focus:border-[#315C50] transition-colors"
              placeholder="••••••••"
            />
          </div>

          <button
            type="submit"
            disabled={submitting}
            className="w-full h-11 rounded-lg bg-[#173B35] hover:bg-[#1f4b43] disabled:opacity-60 disabled:cursor-not-allowed text-white text-sm font-semibold transition-colors flex items-center justify-center gap-2"
          >
            {submitting && <Loader2 className="w-4 h-4 animate-spin" />}
            {submitting ? "Resetting..." : "Reset password"}
          </button>
        </form>
      </div>
    </div>
  );
}
