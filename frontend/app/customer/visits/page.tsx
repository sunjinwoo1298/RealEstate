"use client";

import React, { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { AlertCircle, CalendarClock, Loader2, Plus } from "lucide-react";
import { useCustomerAuth } from "@/lib/customer-auth-context";
import { customerApiClient, CustomerApiError, CustomerSiteVisit } from "@/lib/customer-api-client";
import { VISIT_STATUS_BADGE_CLASS, VISIT_STATUS_LABEL } from "@/lib/customer-visit-constants";

type Tab = "upcoming" | "past" | "all";

function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString("en-IN", {
    timeZone: "Asia/Kolkata",
    dateStyle: "medium",
    timeStyle: "short",
  });
}

function VisitCard({ visit }: { visit: CustomerSiteVisit }) {
  return (
    <Link
      href={`/customer/visits/${visit.id}`}
      className="flex items-center justify-between gap-4 p-4 hover:bg-[#F7F6F2] transition-colors"
    >
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2 mb-1">
          <span className={`text-[11px] font-semibold px-2 py-0.5 rounded-full ${VISIT_STATUS_BADGE_CLASS[visit.status]}`}>
            {VISIT_STATUS_LABEL[visit.status]}
          </span>
          <span className="text-xs text-[#9EA69F]">{visit.booking_reference}</span>
        </div>
        <p className="text-sm font-semibold text-[#202B28] truncate">{visit.project_name}</p>
        <p className="text-xs text-[#737C76] mt-0.5">{formatDateTime(visit.scheduled_start)} (IST)</p>
      </div>
    </Link>
  );
}

export default function CustomerVisitsPage() {
  const { customer, isLoading } = useCustomerAuth();
  const router = useRouter();

  const [tab, setTab] = useState<Tab>("upcoming");
  const [visits, setVisits] = useState<CustomerSiteVisit[] | null>(null);
  const [loadingData, setLoadingData] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!isLoading && !customer) {
      router.replace("/customer/login?returnTo=/customer/visits");
    }
  }, [isLoading, customer, router]);

  const loadVisits = useCallback(async (activeTab: Tab) => {
    setLoadingData(true);
    setError(null);
    try {
      const result = await customerApiClient.listVisits({
        upcoming: activeTab === "all" ? undefined : activeTab === "upcoming",
        limit: 50,
      });
      setVisits(result.items);
    } catch (err) {
      setError(err instanceof CustomerApiError ? err.message : "Unable to load your site visits. Please try again.");
    } finally {
      setLoadingData(false);
    }
  }, []);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- intentional data fetch on tab/customer change
    if (customer) loadVisits(tab);
  }, [customer, tab, loadVisits]);

  if (isLoading || !customer) {
    return (
      <div className="w-full flex justify-center py-16">
        <Loader2 className="w-5 h-5 text-[#173B35] animate-spin" />
      </div>
    );
  }

  return (
    <div className="w-full max-w-3xl space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-heading font-bold text-xl text-[#202B28]">Site Visits</h1>
          <p className="text-sm text-[#737C76] mt-1">Book and manage your property site-visit appointments.</p>
        </div>
        <Link
          href="/customer/visits/book"
          className="h-10 px-4 rounded-lg bg-[#173B35] hover:bg-[#1f4b43] text-white text-sm font-semibold transition-colors flex items-center gap-1.5 shrink-0"
        >
          <Plus className="w-4 h-4" />
          Book a visit
        </Link>
      </div>

      <div className="flex gap-1 bg-white rounded-xl border border-[#E5E5DE] shadow-xs p-1 w-fit">
        {(["upcoming", "past", "all"] as Tab[]).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-4 py-2 rounded-lg text-sm font-semibold transition-colors capitalize ${
              tab === t ? "bg-[#173B35] text-white" : "text-[#202B28] hover:bg-[#F0F1EC]"
            }`}
          >
            {t}
          </button>
        ))}
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
            <button onClick={() => loadVisits(tab)} className="mt-2 text-xs font-semibold underline">
              Retry
            </button>
          </div>
        </div>
      )}

      {!loadingData && !error && visits && visits.length === 0 && (
        <div className="bg-white rounded-xl border border-[#E5E5DE] shadow-xs p-10 flex flex-col items-center text-center">
          <CalendarClock className="w-8 h-8 text-[#C5C5BB] mb-3" />
          <p className="text-sm text-[#737C76] mb-4">
            {tab === "upcoming"
              ? "You have no upcoming site visits scheduled."
              : tab === "past"
              ? "You have no past site visits."
              : "You haven't booked a site visit yet."}
          </p>
          <Link
            href="/customer/visits/book"
            className="h-10 px-4 rounded-lg bg-[#173B35] hover:bg-[#1f4b43] text-white text-sm font-semibold transition-colors inline-flex items-center gap-1.5"
          >
            <Plus className="w-4 h-4" />
            Book a site visit
          </Link>
        </div>
      )}

      {!loadingData && !error && visits && visits.length > 0 && (
        <div className="bg-white rounded-xl border border-[#E5E5DE] shadow-xs divide-y divide-[#E5E5DE] overflow-hidden">
          {visits.map((visit) => (
            <VisitCard key={visit.id} visit={visit} />
          ))}
        </div>
      )}
    </div>
  );
}
