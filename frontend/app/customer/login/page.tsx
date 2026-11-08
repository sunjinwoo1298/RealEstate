"use client";

import React, { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { Loader2, AlertCircle } from "lucide-react";
import { CustomerApiError } from "@/lib/customer-api-client";
import { useCustomerAuth } from "@/lib/customer-auth-context";

function isSafeReturnTo(value: string | null): value is string {
  // Only allow a same-site relative path, never an absolute/external URL,
  // to prevent an open-redirect via a crafted returnTo query parameter.
  return !!value && value.startsWith("/") && !value.startsWith("//");
}

export default function CustomerLoginPage() {
  return (
    <Suspense fallback={<Loader2 className="w-5 h-5 text-[#173B35] animate-spin" />}>
      <CustomerLoginForm />
    </Suspense>
  );
}

function CustomerLoginForm() {
  const { customer, isLoading, login, isSessionExpired, clearSessionExpired } = useCustomerAuth();
  const router = useRouter();
  const searchParams = useSearchParams();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const returnToParam = searchParams.get("returnTo");
  const destination = isSafeReturnTo(returnToParam) ? returnToParam : "/customer/dashboard";

  useEffect(() => {
    if (!isLoading && customer) {
      router.replace(destination);
    }
  }, [isLoading, customer, router, destination]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await login(email, password);
      router.replace(destination);
    } catch (err) {
      setError(err instanceof CustomerApiError ? err.message : "Unable to sign in. Please try again.");
    } finally {
      setSubmitting(false);
    }
  };

  if (isLoading || customer) {
    return <Loader2 className="w-5 h-5 text-[#173B35] animate-spin" />;
  }

  return (
    <div className="w-full max-w-sm">
      <div className="bg-white rounded-xl border border-[#E5E5DE] shadow-xs p-6">
        <h2 className="text-lg font-bold font-heading text-[#202B28] mb-1">Sign in</h2>
        <p className="text-sm text-[#737C76] mb-5">Welcome back.</p>

        {isSessionExpired && (
          <div className="mb-4 flex items-start gap-2 text-sm text-[#B7791F] bg-[#FEF7EC] border border-[#FBE3BC] rounded-lg px-3 py-2.5">
            <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
            <span>Your session expired. Please sign in again.</span>
          </div>
        )}
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
              onChange={(e) => {
                setEmail(e.target.value);
                clearSessionExpired();
              }}
              className="w-full h-11 px-3 rounded-lg border border-[#E5E5DE] bg-white text-sm text-[#202B28] focus:outline-none focus:ring-2 focus:ring-[#315C50] focus:border-[#315C50] transition-colors"
              placeholder="you@example.com"
            />
          </div>
          <div>
            <div className="flex items-center justify-between mb-1.5">
              <label htmlFor="password" className="block text-xs font-semibold text-[#202B28]">
                Password
              </label>
              <Link href="/customer/forgot-password" className="text-xs text-[#173B35] font-semibold hover:underline">
                Forgot password?
              </Link>
            </div>
            <input
              id="password"
              type="password"
              required
              autoComplete="current-password"
              value={password}
              onChange={(e) => {
                setPassword(e.target.value);
                clearSessionExpired();
              }}
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
            {submitting ? "Signing in..." : "Sign in"}
          </button>
        </form>
      </div>

      <p className="text-center text-xs text-[#737C76] mt-6">
        New here?{" "}
        <Link href="/customer/signup" className="text-[#173B35] font-semibold hover:underline">
          Create an account
        </Link>
      </p>
      <p className="text-center text-xs text-[#A3AAA5] mt-2">
        <Link href="/login" className="hover:underline">
          Staff Login
        </Link>
      </p>
    </div>
  );
}
