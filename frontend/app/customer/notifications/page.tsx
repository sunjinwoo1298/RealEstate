"use client";

import React, { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { AlertCircle, Bell, Loader2 } from "lucide-react";
import { useCustomerAuth } from "@/lib/customer-auth-context";
import { customerApiClient, CustomerApiError, CustomerNotification } from "@/lib/customer-api-client";
import {
  NOTIFICATION_EVENT_LABEL,
  NOTIFICATION_STATUS_BADGE_CLASS,
  NOTIFICATION_STATUS_LABEL,
} from "@/lib/customer-visit-constants";

const PAGE_SIZE = 20;

function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString("en-IN", {
    timeZone: "Asia/Kolkata",
    dateStyle: "medium",
    timeStyle: "short",
  });
}

function NotificationRow({ item }: { item: CustomerNotification }) {
  const body = (
    <div className="min-w-0 flex-1">
      <div className="flex items-center gap-2 mb-1">
        <span className="text-sm font-semibold text-[#202B28]">{NOTIFICATION_EVENT_LABEL[item.event_type]}</span>
        <span
          className={`text-[11px] font-semibold px-2 py-0.5 rounded-full ${NOTIFICATION_STATUS_BADGE_CLASS[item.status]}`}
        >
          {NOTIFICATION_STATUS_LABEL[item.status]}
        </span>
      </div>
      {item.project_name && <p className="text-sm text-[#202B28] truncate">{item.project_name}</p>}
      {item.visit_start_time && (
        <p className="text-xs text-[#737C76] mt-0.5">Visit: {formatDateTime(item.visit_start_time)} (IST)</p>
      )}
      <p className="text-xs text-[#9EA69F] mt-0.5">Email &bull; {formatDateTime(item.created_at)} (IST)</p>
    </div>
  );

  if (item.visit_id) {
    return (
      <Link
        href={`/customer/visits/${item.visit_id}`}
        className="flex items-center justify-between gap-4 p-4 hover:bg-[#F7F6F2] transition-colors"
      >
        {body}
      </Link>
    );
  }
  return <div className="flex items-center justify-between gap-4 p-4">{body}</div>;
}

export default function CustomerNotificationsPage() {
  const { customer, isLoading } = useCustomerAuth();
  const router = useRouter();

  const [items, setItems] = useState<CustomerNotification[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [loadingData, setLoadingData] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!isLoading && !customer) {
      router.replace("/customer/login?returnTo=/customer/notifications");
    }
  }, [isLoading, customer, router]);

  const load = useCallback(async (pageOffset: number) => {
    setLoadingData(true);
    setError(null);
    try {
      const result = await customerApiClient.listNotifications({ limit: PAGE_SIZE, offset: pageOffset });
      setItems(result.items);
      setTotal(result.total);
    } catch (err) {
      setError(err instanceof CustomerApiError ? err.message : "Unable to load your notifications. Please try again.");
    } finally {
      setLoadingData(false);
    }
  }, []);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- intentional data fetch on page/customer change
    if (customer) load(offset);
  }, [customer, offset, load]);

  if (isLoading || !customer) {
    return (
      <div className="w-full flex justify-center py-16">
        <Loader2 className="w-5 h-5 text-[#173B35] animate-spin" />
      </div>
    );
  }

  const page = Math.floor(offset / PAGE_SIZE) + 1;
  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <div className="w-full max-w-3xl space-y-6">
      <div>
        <h1 className="font-heading font-bold text-xl text-[#202B28]">Notifications</h1>
        <p className="text-sm text-[#737C76] mt-1">
          Email updates about your site visits. You can manage these in{" "}
          <Link href="/customer/settings" className="underline font-semibold">
            Settings
          </Link>
          .
        </p>
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
            <button onClick={() => load(offset)} className="mt-2 text-xs font-semibold underline">
              Retry
            </button>
          </div>
        </div>
      )}

      {!loadingData && !error && items.length === 0 && (
        <div className="bg-white rounded-xl border border-[#E5E5DE] shadow-xs p-10 flex flex-col items-center text-center">
          <Bell className="w-8 h-8 text-[#C5C5BB] mb-3" />
          <p className="text-sm text-[#737C76]">
            Nothing here yet. Updates about your site-visit bookings, changes and reminders will appear here.
          </p>
        </div>
      )}

      {!loadingData && !error && items.length > 0 && (
        <>
          <div className="bg-white rounded-xl border border-[#E5E5DE] shadow-xs divide-y divide-[#E5E5DE] overflow-hidden">
            {items.map((item) => (
              <NotificationRow key={item.id} item={item} />
            ))}
          </div>
          <div className="flex items-center justify-between text-sm text-[#737C76]">
            <span>
              Page {page} of {pageCount}
            </span>
            <div className="flex gap-2">
              <button
                onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
                disabled={offset === 0}
                className="h-9 px-3 rounded-lg border border-[#E5E5DE] font-semibold text-[#202B28] disabled:opacity-50 hover:bg-[#F0F1EC]"
              >
                Previous
              </button>
              <button
                onClick={() => setOffset(offset + PAGE_SIZE)}
                disabled={offset + PAGE_SIZE >= total}
                className="h-9 px-3 rounded-lg border border-[#E5E5DE] font-semibold text-[#202B28] disabled:opacity-50 hover:bg-[#F0F1EC]"
              >
                Next
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
