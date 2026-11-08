"use client";

import React, { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { AlertCircle, CheckCircle2, Loader2 } from "lucide-react";
import { useCustomerAuth } from "@/lib/customer-auth-context";
import { customerApiClient, CustomerApiError, CustomerProfile } from "@/lib/customer-api-client";

export default function CustomerProfilePage() {
  const { customer, isLoading, refreshCustomer } = useCustomerAuth();
  const router = useRouter();

  const [profile, setProfile] = useState<CustomerProfile | null>(null);
  const [loadingProfile, setLoadingProfile] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [fullName, setFullName] = useState("");
  const [phone, setPhone] = useState("");
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (!isLoading && !customer) {
      router.replace("/customer/login?returnTo=/customer/profile");
    }
  }, [isLoading, customer, router]);

  const loadProfile = useCallback(async () => {
    setLoadingProfile(true);
    setLoadError(null);
    try {
      const result = await customerApiClient.getProfile();
      setProfile(result);
      setFullName(result.full_name);
      setPhone(result.phone || "");
    } catch (err) {
      setLoadError(err instanceof CustomerApiError ? err.message : "Unable to load your profile.");
    } finally {
      setLoadingProfile(false);
    }
  }, []);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- intentional data fetch on customer load
    if (customer) loadProfile();
  }, [customer, loadProfile]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaveError(null);
    setSaved(false);
    setSaving(true);
    try {
      const updated = await customerApiClient.updateProfile({
        full_name: fullName.trim() || undefined,
        phone: phone.trim() || undefined,
      });
      setProfile(updated);
      setSaved(true);
      await refreshCustomer();
    } catch (err) {
      setSaveError(err instanceof CustomerApiError ? err.message : "Unable to save your changes.");
    } finally {
      setSaving(false);
    }
  };

  if (isLoading || !customer) {
    return (
      <div className="w-full flex justify-center py-16">
        <Loader2 className="w-5 h-5 text-[#173B35] animate-spin" />
      </div>
    );
  }

  return (
    <div className="w-full max-w-md">
      <div className="bg-white rounded-xl border border-[#E5E5DE] shadow-xs p-6">
        <h1 className="font-heading font-bold text-xl text-[#202B28] mb-1">My Profile</h1>
        <p className="text-sm text-[#737C76] mb-5">Update your name and phone number.</p>

        {loadingProfile && (
          <div className="flex justify-center py-6">
            <Loader2 className="w-5 h-5 text-[#173B35] animate-spin" />
          </div>
        )}

        {!loadingProfile && loadError && (
          <div className="flex items-start gap-2 text-sm text-[#C34D4D] bg-[#FDF2F2] border border-[#F8D2D2] rounded-lg px-3 py-2.5">
            <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
            <span>{loadError}</span>
          </div>
        )}

        {!loadingProfile && !loadError && profile && (
          <form onSubmit={handleSubmit} className="space-y-4">
            {saveError && (
              <div className="flex items-start gap-2 text-sm text-[#C34D4D] bg-[#FDF2F2] border border-[#F8D2D2] rounded-lg px-3 py-2.5">
                <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
                <span>{saveError}</span>
              </div>
            )}
            {saved && (
              <div className="flex items-start gap-2 text-sm text-[#1F6B4A] bg-[#EAF3EC] border border-[#CFE6D7] rounded-lg px-3 py-2.5">
                <CheckCircle2 className="w-4 h-4 mt-0.5 shrink-0" />
                <span>Your profile has been updated.</span>
              </div>
            )}

            <div>
              <label htmlFor="email" className="block text-xs font-semibold text-[#202B28] mb-1.5">
                Email
              </label>
              <input
                id="email"
                type="email"
                value={profile.email}
                disabled
                className="w-full h-11 px-3 rounded-lg border border-[#E5E5DE] bg-[#F7F6F2] text-sm text-[#737C76] cursor-not-allowed"
              />
            </div>
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
              />
            </div>
            <div>
              <label htmlFor="phone" className="block text-xs font-semibold text-[#202B28] mb-1.5">
                Phone number
              </label>
              <input
                id="phone"
                type="tel"
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
                placeholder="+91 98765 43210"
                className="w-full h-11 px-3 rounded-lg border border-[#E5E5DE] bg-white text-sm text-[#202B28] focus:outline-none focus:ring-2 focus:ring-[#315C50] focus:border-[#315C50] transition-colors"
              />
            </div>

            <button
              type="submit"
              disabled={saving}
              className="w-full h-11 rounded-lg bg-[#173B35] hover:bg-[#1f4b43] disabled:opacity-60 disabled:cursor-not-allowed text-white text-sm font-semibold transition-colors flex items-center justify-center gap-2"
            >
              {saving && <Loader2 className="w-4 h-4 animate-spin" />}
              {saving ? "Saving..." : "Save changes"}
            </button>
          </form>
        )}
      </div>
    </div>
  );
}
