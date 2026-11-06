"use client";

import React, { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Building2, Loader2, AlertCircle } from "lucide-react";
import { ApiError } from "@/lib/api-client";
import { useAuth } from "@/lib/auth-context";

export default function LoginPage() {
  const { user, isLoading, login, isSessionExpired, clearSessionExpired } = useAuth();
  const router = useRouter();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!isLoading && user) {
      router.replace("/");
    }
  }, [isLoading, user, router]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await login(email, password);
      router.replace("/");
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "Unable to sign in. Please try again."
      );
    } finally {
      setSubmitting(false);
    }
  };

  if (isLoading || user) {
    return (
      <div className="h-screen w-screen flex items-center justify-center bg-[#F7F6F2]">
        <Loader2 className="w-5 h-5 text-[#173B35] animate-spin" />
      </div>
    );
  }

  return (
    <div className="min-h-screen w-full flex items-center justify-center bg-[#F7F6F2] px-4">
      <div className="w-full max-w-sm">
        <div className="flex flex-col items-center mb-8">
          <div className="w-12 h-12 rounded-xl bg-[#C47A55] flex items-center justify-center shadow-sm mb-4">
            <Building2 className="w-6 h-6 text-white" />
          </div>
          <h1 className="font-heading font-bold text-xl text-[#202B28] tracking-tight">
            EstateFlow <span className="text-[#C47A55]">AI</span>
          </h1>
          <p className="text-xs text-[#737C76] mt-1 tracking-wide uppercase font-medium">
            Developer Suite
          </p>
        </div>

        <div className="bg-white rounded-xl border border-[#E5E5DE] shadow-xs p-6">
          <h2 className="text-lg font-bold font-heading text-[#202B28] mb-1">
            Sign in
          </h2>
          <p className="text-sm text-[#737C76] mb-5">
            Staff access only. Contact your administrator for an account.
          </p>

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
                placeholder="you@estateflow.ai"
              />
            </div>
            <div>
              <label htmlFor="password" className="block text-xs font-semibold text-[#202B28] mb-1.5">
                Password
              </label>
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
          EstateFlow AI &bull; Real-estate sales automation
        </p>
      </div>
    </div>
  );
}
