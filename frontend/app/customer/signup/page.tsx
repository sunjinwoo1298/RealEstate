"use client";

import React, { useState } from "react";
import Link from "next/link";
import { Loader2, AlertCircle, MailCheck } from "lucide-react";
import { customerApiClient, CustomerApiError } from "@/lib/customer-api-client";

const PASSWORD_HINT = "At least 8 characters, including one letter and one number.";

export default function CustomerSignupPage() {
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [acceptedPrivacyPolicy, setAcceptedPrivacyPolicy] = useState(false);
  const [marketingConsent, setMarketingConsent] = useState(false);

  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [registeredEmail, setRegisteredEmail] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (password !== confirmPassword) {
      setError("Password and confirmation do not match.");
      return;
    }
    if (!acceptedPrivacyPolicy) {
      setError("You must accept the privacy policy and terms to create an account.");
      return;
    }

    setSubmitting(true);
    try {
      const result = await customerApiClient.register({
        full_name: fullName,
        email,
        password,
        password_confirmation: confirmPassword,
        phone: phone.trim() || undefined,
        accepted_privacy_policy: acceptedPrivacyPolicy,
        marketing_consent: marketingConsent,
      });
      setRegisteredEmail(result.email);
    } catch (err) {
      setError(err instanceof CustomerApiError ? err.message : "Unable to create your account. Please try again.");
    } finally {
      setSubmitting(false);
    }
  };

  if (registeredEmail) {
    return (
      <div className="w-full max-w-sm text-center">
        <div className="w-14 h-14 rounded-full bg-[#E9F5EF] text-[#27845B] flex items-center justify-center mx-auto">
          <MailCheck className="w-7 h-7" />
        </div>
        <h1 className="font-heading font-bold text-xl text-[#202B28] mt-5">Check your email</h1>
        <p className="text-sm text-[#737C76] mt-3 leading-relaxed">
          We&apos;ve sent a verification link to <span className="font-semibold text-[#202B28]">{registeredEmail}</span>.
          Please verify your address before signing in.
        </p>
        <Link
          href="/customer/verify-email"
          className="inline-flex items-center justify-center mt-6 h-11 px-5 rounded-lg bg-[#173B35] hover:bg-[#1f4b43] text-white text-sm font-semibold transition-colors"
        >
          I have a verification link
        </Link>
      </div>
    );
  }

  return (
    <div className="w-full max-w-sm">
      <div className="bg-white rounded-xl border border-[#E5E5DE] shadow-xs p-6">
        <h2 className="text-lg font-bold font-heading text-[#202B28] mb-1">Create your account</h2>
        <p className="text-sm text-[#737C76] mb-5">
          Save favourite projects, chat with our AI assistant, and book site visits.
        </p>

        {error && (
          <div className="mb-4 flex items-start gap-2 text-sm text-[#C34D4D] bg-[#FDF2F2] border border-[#F8D2D2] rounded-lg px-3 py-2.5">
            <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label htmlFor="full_name" className="block text-xs font-semibold text-[#202B28] mb-1.5">
              Full name
            </label>
            <input
              id="full_name"
              type="text"
              required
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              className="w-full h-11 px-3 rounded-lg border border-[#E5E5DE] bg-white text-sm text-[#202B28] focus:outline-none focus:ring-2 focus:ring-[#315C50] focus:border-[#315C50] transition-colors"
              placeholder="Jane Doe"
            />
          </div>
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
          <div>
            <label htmlFor="phone" className="block text-xs font-semibold text-[#202B28] mb-1.5">
              Phone <span className="text-[#A3AAA5] font-normal">(optional)</span>
            </label>
            <input
              id="phone"
              type="tel"
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              className="w-full h-11 px-3 rounded-lg border border-[#E5E5DE] bg-white text-sm text-[#202B28] focus:outline-none focus:ring-2 focus:ring-[#315C50] focus:border-[#315C50] transition-colors"
              placeholder="+91 98765 43210"
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
              minLength={8}
              autoComplete="new-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full h-11 px-3 rounded-lg border border-[#E5E5DE] bg-white text-sm text-[#202B28] focus:outline-none focus:ring-2 focus:ring-[#315C50] focus:border-[#315C50] transition-colors"
              placeholder="••••••••"
            />
            <p className="text-xs text-[#A3AAA5] mt-1">{PASSWORD_HINT}</p>
          </div>
          <div>
            <label htmlFor="confirm_password" className="block text-xs font-semibold text-[#202B28] mb-1.5">
              Confirm password
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

          <label className="flex items-start gap-2.5 text-xs text-[#202B28] cursor-pointer">
            <input
              type="checkbox"
              required
              checked={acceptedPrivacyPolicy}
              onChange={(e) => setAcceptedPrivacyPolicy(e.target.checked)}
              className="mt-0.5 w-4 h-4 accent-[#173B35]"
            />
            <span>
              I agree to the{" "}
              <Link href="/terms" className="text-[#173B35] font-semibold hover:underline">
                Terms &amp; Conditions
              </Link>{" "}
              and{" "}
              <Link href="/privacy" className="text-[#173B35] font-semibold hover:underline">
                Privacy Policy
              </Link>
              . <span className="text-[#C34D4D]">*</span>
            </span>
          </label>

          <label className="flex items-start gap-2.5 text-xs text-[#202B28] cursor-pointer">
            <input
              type="checkbox"
              checked={marketingConsent}
              onChange={(e) => setMarketingConsent(e.target.checked)}
              className="mt-0.5 w-4 h-4 accent-[#173B35]"
            />
            <span>Send me project updates and offers by email (optional).</span>
          </label>

          <button
            type="submit"
            disabled={submitting}
            className="w-full h-11 rounded-lg bg-[#173B35] hover:bg-[#1f4b43] disabled:opacity-60 disabled:cursor-not-allowed text-white text-sm font-semibold transition-colors flex items-center justify-center gap-2"
          >
            {submitting && <Loader2 className="w-4 h-4 animate-spin" />}
            {submitting ? "Creating account..." : "Create account"}
          </button>
        </form>
      </div>

      <p className="text-center text-xs text-[#737C76] mt-6">
        Already have an account?{" "}
        <Link href="/customer/login" className="text-[#173B35] font-semibold hover:underline">
          Sign in
        </Link>
      </p>
    </div>
  );
}
