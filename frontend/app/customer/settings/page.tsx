"use client";

import React, { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { AlertCircle, CheckCircle2, Loader2 } from "lucide-react";
import { useCustomerAuth } from "@/lib/customer-auth-context";
import {
  customerApiClient,
  CustomerApiError,
  CustomerProfile,
  NotificationPreferences,
} from "@/lib/customer-api-client";

export default function CustomerSettingsPage() {
  const { customer, isLoading, logout } = useCustomerAuth();
  const router = useRouter();

  const [profile, setProfile] = useState<CustomerProfile | null>(null);
  const [loadingProfile, setLoadingProfile] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [changing, setChanging] = useState(false);
  const [changeError, setChangeError] = useState<string | null>(null);
  const [changeSuccess, setChangeSuccess] = useState<string | null>(null);

  const [prefs, setPrefs] = useState<NotificationPreferences | null>(null);
  const [prefsError, setPrefsError] = useState<string | null>(null);
  const [savingPrefs, setSavingPrefs] = useState(false);

  useEffect(() => {
    if (!isLoading && !customer) {
      router.replace("/customer/login?returnTo=/customer/settings");
    }
  }, [isLoading, customer, router]);

  const loadProfile = useCallback(async () => {
    setLoadingProfile(true);
    setLoadError(null);
    try {
      const result = await customerApiClient.getProfile();
      setProfile(result);
    } catch (err) {
      setLoadError(err instanceof CustomerApiError ? err.message : "Unable to load account settings.");
    } finally {
      setLoadingProfile(false);
    }
  }, []);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- intentional data fetch on customer load
    if (customer) loadProfile();
  }, [customer, loadProfile]);

  useEffect(() => {
    if (!customer) return;
    customerApiClient
      .getNotificationPreferences()
      .then(setPrefs)
      .catch((err) =>
        setPrefsError(err instanceof CustomerApiError ? err.message : "Unable to load email preferences.")
      );
  }, [customer]);

  const handleToggleTransactional = async (enabled: boolean) => {
    setSavingPrefs(true);
    setPrefsError(null);
    try {
      setPrefs(await customerApiClient.updateNotificationPreferences(enabled));
    } catch (err) {
      setPrefsError(err instanceof CustomerApiError ? err.message : "Unable to save your email preference.");
    } finally {
      setSavingPrefs(false);
    }
  };

  const handleChangePassword = async (e: React.FormEvent) => {
    e.preventDefault();
    setChangeError(null);
    setChangeSuccess(null);

    if (newPassword !== confirmPassword) {
      setChangeError("New password and confirmation do not match.");
      return;
    }

    setChanging(true);
    try {
      const result = await customerApiClient.changePassword(currentPassword, newPassword, confirmPassword);
      setChangeSuccess(result.message);
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
      // The backend has already revoked every refresh session for this
      // account -- clear local/frontend state too and send the customer
      // back to sign in, matching the "clear response requiring the
      // customer to sign in again" requirement.
      setTimeout(() => {
        logout().finally(() => router.replace("/customer/login"));
      }, 1500);
    } catch (err) {
      setChangeError(err instanceof CustomerApiError ? err.message : "Unable to change your password.");
    } finally {
      setChanging(false);
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
    <div className="w-full max-w-md space-y-6">
      <div className="bg-white rounded-xl border border-[#E5E5DE] shadow-xs p-6">
        <h1 className="font-heading font-bold text-xl text-[#202B28] mb-1">Account Settings</h1>
        <p className="text-sm text-[#737C76] mb-5">Your account details and security options.</p>

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
          <dl className="space-y-3 text-sm">
            <div className="flex justify-between">
              <dt className="text-[#737C76]">Email</dt>
              <dd className="font-semibold text-[#202B28]">{profile.email}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-[#737C76]">Email verification</dt>
              <dd className={`font-semibold ${profile.email_verified ? "text-[#1F6B4A]" : "text-[#B7791F]"}`}>
                {profile.email_verified ? "Verified" : "Not verified"}
              </dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-[#737C76]">Account status</dt>
              <dd className="font-semibold text-[#202B28]">{profile.status}</dd>
            </div>
          </dl>
        )}
      </div>

      <div className="bg-white rounded-xl border border-[#E5E5DE] shadow-xs p-6">
        <h2 className="font-heading font-bold text-base text-[#202B28] mb-1">Email notifications</h2>
        <p className="text-sm text-[#737C76] mb-4">
          Essential visit updates are service messages about a site visit you requested: booking confirmations,
          reschedule and cancellation notices, and reminders 24 hours and 2 hours before your visit. They are sent only
          to your verified email address and are separate from marketing.
        </p>
        {prefsError && (
          <div className="mb-4 flex items-start gap-2 text-sm text-[#C34D4D] bg-[#FDF2F2] border border-[#F8D2D2] rounded-lg px-3 py-2.5">
            <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
            <span>{prefsError}</span>
          </div>
        )}
        {prefs && (
          <>
            <label className="flex items-start gap-3 cursor-pointer">
              <input
                type="checkbox"
                className="mt-1 h-4 w-4 accent-[#173B35]"
                checked={prefs.transactional_email_enabled}
                disabled={savingPrefs}
                onChange={(e) => handleToggleTransactional(e.target.checked)}
              />
              <span className="text-sm text-[#202B28]">
                <span className="font-semibold">Essential visit updates by email</span>
                <span className="block text-xs text-[#737C76] mt-0.5">
                  If you turn this off, you will not receive booking confirmations or reminders by email. You can still
                  see your visits under Visits.
                </span>
              </span>
            </label>
            {!prefs.email_verified && (
              <p className="mt-3 text-xs text-[#B7791F]">Your email is not verified, so no emails will be sent.</p>
            )}
            <p className="mt-4 text-xs text-[#737C76]">
              We do not send marketing email today. If that changes, we will ask for your separate consent first.
            </p>
          </>
        )}
      </div>

      <div className="bg-white rounded-xl border border-[#E5E5DE] shadow-xs p-6">
        <h2 className="font-heading font-bold text-base text-[#202B28] mb-4">Change password</h2>

        {changeError && (
          <div className="mb-4 flex items-start gap-2 text-sm text-[#C34D4D] bg-[#FDF2F2] border border-[#F8D2D2] rounded-lg px-3 py-2.5">
            <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
            <span>{changeError}</span>
          </div>
        )}
        {changeSuccess && (
          <div className="mb-4 flex items-start gap-2 text-sm text-[#1F6B4A] bg-[#EAF3EC] border border-[#CFE6D7] rounded-lg px-3 py-2.5">
            <CheckCircle2 className="w-4 h-4 mt-0.5 shrink-0" />
            <span>{changeSuccess}</span>
          </div>
        )}

        <form onSubmit={handleChangePassword} className="space-y-4">
          <div>
            <label htmlFor="current_password" className="block text-xs font-semibold text-[#202B28] mb-1.5">
              Current password
            </label>
            <input
              id="current_password"
              type="password"
              required
              autoComplete="current-password"
              value={currentPassword}
              onChange={(e) => setCurrentPassword(e.target.value)}
              className="w-full h-11 px-3 rounded-lg border border-[#E5E5DE] bg-white text-sm text-[#202B28] focus:outline-none focus:ring-2 focus:ring-[#315C50] focus:border-[#315C50] transition-colors"
            />
          </div>
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
            />
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
            />
          </div>
          <button
            type="submit"
            disabled={changing}
            className="w-full h-11 rounded-lg bg-[#173B35] hover:bg-[#1f4b43] disabled:opacity-60 disabled:cursor-not-allowed text-white text-sm font-semibold transition-colors flex items-center justify-center gap-2"
          >
            {changing && <Loader2 className="w-4 h-4 animate-spin" />}
            {changing ? "Changing..." : "Change password"}
          </button>
        </form>
      </div>

      <div className="bg-white rounded-xl border border-[#E5E5DE] shadow-xs p-6">
        <button
          onClick={() => logout()}
          className="w-full h-10 rounded-lg border border-[#E5E5DE] text-sm font-semibold text-[#202B28] hover:bg-[#F0F1EC] transition-colors"
        >
          Sign out
        </button>
      </div>
    </div>
  );
}
