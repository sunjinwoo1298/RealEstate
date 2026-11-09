"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import {
  AlertCircle,
  AlertTriangle,
  ArrowLeft,
  Bell,
  CalendarDays,
  Clock,
  Loader2,
  User,
} from "lucide-react";
import { useCustomerAuth } from "@/lib/customer-auth-context";
import {
  customerApiClient,
  CustomerApiError,
  CustomerAvailableSlot,
  CustomerSiteVisit,
} from "@/lib/customer-api-client";
import {
  REMINDER_STATUS_LABEL,
  VISIT_STATUS_BADGE_CLASS,
  VISIT_STATUS_LABEL,
} from "@/lib/customer-visit-constants";

function todayIsoDate(): string {
  const now = new Date();
  const offset = now.getTimezoneOffset();
  return new Date(now.getTime() - offset * 60000).toISOString().slice(0, 10);
}

function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString("en-IN", { timeZone: "Asia/Kolkata", dateStyle: "medium", timeStyle: "short" });
}

function formatSlotTime(iso: string): string {
  return new Date(iso).toLocaleTimeString("en-IN", { timeZone: "Asia/Kolkata", hour: "2-digit", minute: "2-digit" });
}

export default function CustomerVisitDetailPage() {
  const { customer, isLoading } = useCustomerAuth();
  const router = useRouter();
  const params = useParams<{ visitId: string }>();
  const visitId = params.visitId;

  const [visit, setVisit] = useState<CustomerSiteVisit | null>(null);
  const [loadingData, setLoadingData] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notFound, setNotFound] = useState(false);

  const [showReschedule, setShowReschedule] = useState(false);
  const [rescheduleDate, setRescheduleDate] = useState(todayIsoDate());
  const [rescheduleSlots, setRescheduleSlots] = useState<CustomerAvailableSlot[] | null>(null);
  const [rescheduleSlotsLoading, setRescheduleSlotsLoading] = useState(false);
  const [selectedSlot, setSelectedSlot] = useState<CustomerAvailableSlot | null>(null);
  const rescheduleSlotsRequestRef = useRef(0);
  const [rescheduling, setRescheduling] = useState(false);
  const [rescheduleError, setRescheduleError] = useState<string | null>(null);

  const [showCancelConfirm, setShowCancelConfirm] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const [cancelError, setCancelError] = useState<string | null>(null);

  useEffect(() => {
    if (!isLoading && !customer) {
      router.replace(`/customer/login?returnTo=/customer/visits/${visitId}`);
    }
  }, [isLoading, customer, router, visitId]);

  const loadVisit = useCallback(async () => {
    setLoadingData(true);
    setError(null);
    setNotFound(false);
    try {
      const result = await customerApiClient.getVisit(visitId);
      setVisit(result);
    } catch (err) {
      if (err instanceof CustomerApiError && err.status === 404) {
        setNotFound(true);
      } else {
        setError(err instanceof CustomerApiError ? err.message : "Unable to load this booking. Please try again.");
      }
    } finally {
      setLoadingData(false);
    }
  }, [visitId]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- intentional data fetch on customer/id load
    if (customer) loadVisit();
  }, [customer, loadVisit]);

  const loadRescheduleSlots = useCallback(async () => {
    if (!visit) return;
    // Ignore responses from superseded requests (an earlier date's slots
    // resolving after the current date's would otherwise replace them).
    const requestId = ++rescheduleSlotsRequestRef.current;
    setRescheduleSlots(null);
    setRescheduleSlotsLoading(true);
    setSelectedSlot(null);
    try {
      const result = await customerApiClient.getVisitAvailability(visit.project_id, rescheduleDate);
      if (requestId === rescheduleSlotsRequestRef.current) setRescheduleSlots(result.slots);
    } catch (err) {
      if (requestId === rescheduleSlotsRequestRef.current) {
        setRescheduleError(err instanceof CustomerApiError ? err.message : "Unable to load available slots.");
      }
    } finally {
      if (requestId === rescheduleSlotsRequestRef.current) setRescheduleSlotsLoading(false);
    }
  }, [visit, rescheduleDate]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- intentional slot refetch on date change
    if (showReschedule) loadRescheduleSlots();
  }, [showReschedule, loadRescheduleSlots]);

  const handleReschedule = async () => {
    if (!selectedSlot || rescheduling) return;
    setRescheduling(true);
    setRescheduleError(null);
    try {
      const updated = await customerApiClient.rescheduleVisit(visitId, {
        scheduled_start: selectedSlot.start_time,
        scheduled_end: selectedSlot.end_time,
      });
      setVisit(updated);
      setShowReschedule(false);
      setSelectedSlot(null);
    } catch (err) {
      if (err instanceof CustomerApiError && err.status === 409) {
        setRescheduleError(`${err.message} Please choose a different slot.`);
        await loadRescheduleSlots();
      } else {
        setRescheduleError(err instanceof CustomerApiError ? err.message : "Failed to reschedule. Please try again.");
      }
    } finally {
      setRescheduling(false);
    }
  };

  const handleCancel = async () => {
    if (cancelling) return;
    setCancelling(true);
    setCancelError(null);
    try {
      const updated = await customerApiClient.cancelVisit(visitId);
      setVisit(updated);
      setShowCancelConfirm(false);
    } catch (err) {
      setCancelError(err instanceof CustomerApiError ? err.message : "Failed to cancel this booking. Please try again.");
    } finally {
      setCancelling(false);
    }
  };

  if (isLoading || !customer) {
    return (
      <div className="w-full flex justify-center py-16">
        <Loader2 className="w-5 h-5 text-[#173B35] animate-spin" />
      </div>
    );
  }

  const canModify = visit?.status === "CONFIRMED";

  return (
    <div className="w-full max-w-2xl space-y-6">
      <Link href="/customer/visits" className="inline-flex items-center gap-1.5 text-sm text-[#737C76] hover:text-[#173B35]">
        <ArrowLeft className="w-3.5 h-3.5" />
        Back to my visits
      </Link>

      {loadingData && (
        <div className="flex justify-center py-16">
          <Loader2 className="w-5 h-5 text-[#173B35] animate-spin" />
        </div>
      )}

      {!loadingData && notFound && (
        <div className="bg-white rounded-xl border border-[#E5E5DE] shadow-xs p-10 text-center">
          <p className="text-sm text-[#737C76]">This booking could not be found.</p>
        </div>
      )}

      {!loadingData && error && (
        <div className="bg-white rounded-xl border border-[#F8D2D2] shadow-xs p-6 flex items-start gap-2 text-sm text-[#C34D4D]">
          <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
          <div>
            <p>{error}</p>
            <button onClick={loadVisit} className="mt-2 text-xs font-semibold underline">
              Retry
            </button>
          </div>
        </div>
      )}

      {!loadingData && !error && !notFound && visit && (
        <>
          <div className="bg-white rounded-xl border border-[#E5E5DE] shadow-xs p-6 space-y-5">
            <div className="flex items-start justify-between">
              <div>
                <h1 className="font-heading font-bold text-xl text-[#202B28]">{visit.project_name}</h1>
                <p className="text-xs text-[#9EA69F] mt-1">{visit.booking_reference}</p>
              </div>
              <span className={`text-xs font-semibold px-2.5 py-1 rounded-full ${VISIT_STATUS_BADGE_CLASS[visit.status]}`}>
                {VISIT_STATUS_LABEL[visit.status]}
              </span>
            </div>

            <dl className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-sm">
              <div>
                <dt className="text-[#737C76] flex items-center gap-1.5">
                  <CalendarDays className="w-3.5 h-3.5" /> Scheduled
                </dt>
                <dd className="font-semibold text-[#202B28] mt-0.5">{formatDateTime(visit.scheduled_start)}</dd>
              </div>
              <div>
                <dt className="text-[#737C76] flex items-center gap-1.5">
                  <Clock className="w-3.5 h-3.5" /> Timezone
                </dt>
                <dd className="font-semibold text-[#202B28] mt-0.5">{visit.display_timezone}</dd>
              </div>
              {visit.executive_full_name && (
                <div>
                  <dt className="text-[#737C76] flex items-center gap-1.5">
                    <User className="w-3.5 h-3.5" /> Sales representative
                  </dt>
                  <dd className="font-semibold text-[#202B28] mt-0.5">{visit.executive_full_name}</dd>
                </div>
              )}
            </dl>

            {(visit.reminder_24h || visit.reminder_2h) && (
              <div className="pt-4 border-t border-[#F0F1EC]">
                <p className="text-xs font-semibold text-[#202B28] mb-2 flex items-center gap-1.5">
                  <Bell className="w-3.5 h-3.5" /> Reminders
                </p>
                <div className="flex gap-4 text-xs text-[#737C76]">
                  {visit.reminder_24h && <span>24h before: {REMINDER_STATUS_LABEL[visit.reminder_24h.status]}</span>}
                  {visit.reminder_2h && <span>2h before: {REMINDER_STATUS_LABEL[visit.reminder_2h.status]}</span>}
                </div>
              </div>
            )}

            {canModify && (
              <div className="flex gap-3 pt-4 border-t border-[#F0F1EC]">
                <button
                  onClick={() => setShowReschedule((v) => !v)}
                  className="flex-1 h-10 rounded-lg border border-[#E5E5DE] text-sm font-semibold text-[#202B28] hover:bg-[#F0F1EC] transition-colors"
                >
                  Reschedule
                </button>
                <button
                  onClick={() => setShowCancelConfirm(true)}
                  className="flex-1 h-10 rounded-lg border border-[#F8D2D2] text-sm font-semibold text-[#C34D4D] hover:bg-[#FDF2F2] transition-colors"
                >
                  Cancel visit
                </button>
              </div>
            )}
          </div>

          {showReschedule && canModify && (
            <div className="bg-white rounded-xl border border-[#E5E5DE] shadow-xs p-6 space-y-4">
              <h2 className="font-heading font-bold text-base text-[#202B28]">Choose a new date &amp; time</h2>
              <input
                type="date"
                value={rescheduleDate}
                min={todayIsoDate()}
                onChange={(e) => setRescheduleDate(e.target.value)}
                className="w-full h-10 px-3 rounded-lg border border-[#E5E5DE] text-sm focus:outline-none focus:ring-2 focus:ring-[#315C50]"
              />

              {rescheduleSlotsLoading && (
                <div className="flex items-center gap-2 text-sm text-[#737C76] py-2">
                  <Loader2 className="w-4 h-4 animate-spin" /> Loading available slots...
                </div>
              )}
              {!rescheduleSlotsLoading && rescheduleSlots && rescheduleSlots.length === 0 && (
                <p className="text-sm text-[#737C76]">No slots are available on this date. Try another date.</p>
              )}
              {!rescheduleSlotsLoading && rescheduleSlots && rescheduleSlots.length > 0 && (
                <div className="flex flex-wrap gap-2">
                  {rescheduleSlots.map((slot) => (
                    <button
                      key={slot.start_time}
                      onClick={() => setSelectedSlot(slot)}
                      className={`h-9 px-3 rounded-lg border text-xs font-semibold transition-colors ${
                        selectedSlot?.start_time === slot.start_time
                          ? "border-[#173B35] bg-[#173B35] text-white"
                          : "border-[#315C50] text-[#173B35] hover:bg-[#E9F5EF]"
                      }`}
                    >
                      {formatSlotTime(slot.start_time)}
                    </button>
                  ))}
                </div>
              )}

              {rescheduleError && <p className="text-sm text-[#C34D4D]">{rescheduleError}</p>}

              <div className="flex gap-3">
                <button
                  onClick={() => setShowReschedule(false)}
                  disabled={rescheduling}
                  className="flex-1 h-10 rounded-lg border border-[#E5E5DE] text-sm font-semibold text-[#202B28] hover:bg-[#F0F1EC] transition-colors disabled:opacity-40"
                >
                  Cancel
                </button>
                <button
                  onClick={handleReschedule}
                  disabled={!selectedSlot || rescheduling}
                  className="flex-1 h-10 rounded-lg bg-[#173B35] hover:bg-[#1f4b43] text-white text-sm font-semibold transition-colors disabled:opacity-40 flex items-center justify-center gap-2"
                >
                  {rescheduling && <Loader2 className="w-4 h-4 animate-spin" />}
                  Confirm new time
                </button>
              </div>
            </div>
          )}

          {showCancelConfirm && (
            <div className="bg-white rounded-xl border border-[#F8D2D2] shadow-xs p-6 space-y-4">
              <div className="flex items-start gap-2">
                <AlertTriangle className="w-5 h-5 text-[#C34D4D] shrink-0 mt-0.5" />
                <div>
                  <h2 className="font-heading font-bold text-base text-[#202B28]">Cancel this site visit?</h2>
                  <p className="text-sm text-[#737C76] mt-1">
                    Your booking for {formatDateTime(visit.scheduled_start)} will be cancelled. This cannot be undone.
                  </p>
                </div>
              </div>
              {cancelError && <p className="text-sm text-[#C34D4D]">{cancelError}</p>}
              <div className="flex gap-3">
                <button
                  onClick={() => setShowCancelConfirm(false)}
                  disabled={cancelling}
                  className="flex-1 h-10 rounded-lg border border-[#E5E5DE] text-sm font-semibold text-[#202B28] hover:bg-[#F0F1EC] transition-colors disabled:opacity-40"
                >
                  Keep booking
                </button>
                <button
                  onClick={handleCancel}
                  disabled={cancelling}
                  className="flex-1 h-10 rounded-lg bg-[#C34D4D] hover:bg-[#B23D3D] text-white text-sm font-semibold transition-colors disabled:opacity-60 flex items-center justify-center gap-2"
                >
                  {cancelling && <Loader2 className="w-4 h-4 animate-spin" />}
                  Yes, cancel visit
                </button>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
