"use client";

import React, { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import {
  AlertCircle,
  Building2,
  CalendarClock,
  Loader2,
  LogOut,
  MessageSquare,
  Settings as SettingsIcon,
  UserCircle2,
} from "lucide-react";
import { useCustomerAuth } from "@/lib/customer-auth-context";
import {
  customerApiClient,
  CustomerApiError,
  CustomerEnquirySummary,
  CustomerProfile,
} from "@/lib/customer-api-client";

export default function CustomerDashboardPage() {
  const { customer, isLoading, logout } = useCustomerAuth();
  const router = useRouter();

  const [profile, setProfile] = useState<CustomerProfile | null>(null);
  const [enquiry, setEnquiry] = useState<CustomerEnquirySummary | null>(null);
  const [loadingData, setLoadingData] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!isLoading && !customer) {
      router.replace("/customer/login?returnTo=/customer/dashboard");
    }
  }, [isLoading, customer, router]);

  const loadDashboard = useCallback(async () => {
    setLoadingData(true);
    setError(null);
    try {
      const [profileResult, enquiryResult] = await Promise.all([
        customerApiClient.getProfile(),
        customerApiClient.getEnquiry(),
      ]);
      setProfile(profileResult);
      setEnquiry(enquiryResult);
    } catch (err) {
      setError(err instanceof CustomerApiError ? err.message : "Unable to load your dashboard. Please try again.");
    } finally {
      setLoadingData(false);
    }
  }, []);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- intentional data fetch on customer load
    if (customer) loadDashboard();
  }, [customer, loadDashboard]);

  if (isLoading || !customer) {
    return (
      <div className="w-full flex justify-center py-16">
        <Loader2 className="w-5 h-5 text-[#173B35] animate-spin" />
      </div>
    );
  }

  return (
    <div className="w-full max-w-3xl space-y-6">
      {/* A. Welcome section */}
      <div className="bg-white rounded-xl border border-[#E5E5DE] shadow-xs p-6">
        <h1 className="font-heading font-bold text-xl text-[#202B28]">
          Welcome back, {customer.full_name.split(" ")[0]}
        </h1>
        <p className="text-sm text-[#737C76] mt-1">Here&apos;s an overview of your EstateFlow account.</p>
        <div className="flex flex-wrap gap-2 mt-4">
          <span
            className={`text-xs font-semibold px-2.5 py-1 rounded-full ${
              customer.email_verified ? "bg-[#EAF3EC] text-[#1F6B4A]" : "bg-[#FEF7EC] text-[#B7791F]"
            }`}
          >
            {customer.email_verified ? "Email verified" : "Email not verified"}
          </span>
          <span
            className={`text-xs font-semibold px-2.5 py-1 rounded-full ${
              customer.lead_linked ? "bg-[#EAF3EC] text-[#1F6B4A]" : "bg-[#F0F1EC] text-[#737C76]"
            }`}
          >
            {customer.lead_linked ? "Enquiry linked" : "No enquiry yet"}
          </span>
        </div>
      </div>

      {loadingData && (
        <div className="flex justify-center py-10">
          <Loader2 className="w-5 h-5 text-[#173B35] animate-spin" />
        </div>
      )}

      {!loadingData && error && (
        <div className="bg-white rounded-xl border border-[#F8D2D2] shadow-xs p-6 flex items-start gap-2 text-sm text-[#C34D4D]">
          <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
          <div>
            <p>{error}</p>
            <button onClick={loadDashboard} className="mt-2 text-xs font-semibold underline">
              Retry
            </button>
          </div>
        </div>
      )}

      {/* B. Account overview */}
      {!loadingData && !error && profile && (
        <div className="bg-white rounded-xl border border-[#E5E5DE] shadow-xs p-6">
          <h2 className="font-heading font-bold text-base text-[#202B28] mb-4">Account overview</h2>
          <dl className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-sm">
            <div>
              <dt className="text-[#737C76]">Name</dt>
              <dd className="font-semibold text-[#202B28]">{profile.full_name}</dd>
            </div>
            <div>
              <dt className="text-[#737C76]">Email</dt>
              <dd className="font-semibold text-[#202B28]">{profile.email}</dd>
            </div>
            <div>
              <dt className="text-[#737C76]">Phone</dt>
              <dd className="font-semibold text-[#202B28]">{profile.phone || "Not provided"}</dd>
            </div>
            <div>
              <dt className="text-[#737C76]">Member since</dt>
              <dd className="font-semibold text-[#202B28]">
                {new Date(profile.created_at).toLocaleDateString()}
              </dd>
            </div>
          </dl>
          <div className="mt-5">
            <div className="flex items-center justify-between text-xs text-[#737C76] mb-1.5">
              <span>Profile completeness</span>
              <span className="font-semibold text-[#202B28]">{profile.profile_completeness}%</span>
            </div>
            <div className="h-2 rounded-full bg-[#F0F1EC] overflow-hidden">
              <div
                className="h-full bg-[#C47A55] rounded-full"
                style={{ width: `${profile.profile_completeness}%` }}
              />
            </div>
          </div>
        </div>
      )}

      {/* C. Enquiry overview */}
      {!loadingData && !error && enquiry && (
        <div className="bg-white rounded-xl border border-[#E5E5DE] shadow-xs p-6">
          <h2 className="font-heading font-bold text-base text-[#202B28] mb-4">Your enquiry</h2>
          {enquiry.has_enquiry ? (
            <dl className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-sm">
              <div>
                <dt className="text-[#737C76]">Reference</dt>
                <dd className="font-semibold text-[#202B28]">{enquiry.enquiry_reference}</dd>
              </div>
              <div>
                <dt className="text-[#737C76]">Status</dt>
                <dd className="font-semibold text-[#202B28]">{enquiry.customer_status}</dd>
              </div>
              <div>
                <dt className="text-[#737C76]">Project</dt>
                <dd className="font-semibold text-[#202B28]">{enquiry.project_name || "Unavailable"}</dd>
              </div>
              <div>
                <dt className="text-[#737C76]">Configuration</dt>
                <dd className="font-semibold text-[#202B28]">{enquiry.configuration || "Not specified"}</dd>
              </div>
              <div>
                <dt className="text-[#737C76]">Enquiry date</dt>
                <dd className="font-semibold text-[#202B28]">
                  {enquiry.enquiry_date ? new Date(enquiry.enquiry_date).toLocaleDateString() : "--"}
                </dd>
              </div>
            </dl>
          ) : (
            <div>
              <p className="text-sm text-[#737C76]">No enquiry is currently associated with your account.</p>
              <Link href="/projects" className="inline-block mt-3 text-sm font-semibold text-[#173B35] hover:underline">
                Browse projects &rarr;
              </Link>
            </div>
          )}
        </div>
      )}

      {/* D. Quick actions */}
      <div className="bg-white rounded-xl border border-[#E5E5DE] shadow-xs p-6">
        <h2 className="font-heading font-bold text-base text-[#202B28] mb-4">Quick actions</h2>
        <div className="grid grid-cols-2 sm:grid-cols-6 gap-3">
          <Link
            href="/customer/chat"
            className="flex flex-col items-center gap-2 p-4 rounded-lg border border-[#E5E5DE] hover:bg-[#F7F6F2] transition-colors text-center"
          >
            <MessageSquare className="w-5 h-5 text-[#173B35]" />
            <span className="text-xs font-semibold text-[#202B28]">Chat with us</span>
          </Link>
          <Link
            href="/customer/visits/book"
            className="flex flex-col items-center gap-2 p-4 rounded-lg border border-[#E5E5DE] hover:bg-[#F7F6F2] transition-colors text-center"
          >
            <CalendarClock className="w-5 h-5 text-[#173B35]" />
            <span className="text-xs font-semibold text-[#202B28]">Book a Visit</span>
          </Link>
          <Link
            href="/customer/profile"
            className="flex flex-col items-center gap-2 p-4 rounded-lg border border-[#E5E5DE] hover:bg-[#F7F6F2] transition-colors text-center"
          >
            <UserCircle2 className="w-5 h-5 text-[#173B35]" />
            <span className="text-xs font-semibold text-[#202B28]">Edit Profile</span>
          </Link>
          <Link
            href="/projects"
            className="flex flex-col items-center gap-2 p-4 rounded-lg border border-[#E5E5DE] hover:bg-[#F7F6F2] transition-colors text-center"
          >
            <Building2 className="w-5 h-5 text-[#173B35]" />
            <span className="text-xs font-semibold text-[#202B28]">Browse Projects</span>
          </Link>
          <Link
            href="/customer/settings"
            className="flex flex-col items-center gap-2 p-4 rounded-lg border border-[#E5E5DE] hover:bg-[#F7F6F2] transition-colors text-center"
          >
            <SettingsIcon className="w-5 h-5 text-[#173B35]" />
            <span className="text-xs font-semibold text-[#202B28]">Account Settings</span>
          </Link>
          <button
            onClick={() => logout()}
            className="flex flex-col items-center gap-2 p-4 rounded-lg border border-[#E5E5DE] hover:bg-[#F7F6F2] transition-colors text-center"
          >
            <LogOut className="w-5 h-5 text-[#173B35]" />
            <span className="text-xs font-semibold text-[#202B28]">Sign Out</span>
          </button>
        </div>
      </div>
    </div>
  );
}
