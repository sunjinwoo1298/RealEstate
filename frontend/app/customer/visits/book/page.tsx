"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import {
  AlertCircle,
  ArrowLeft,
  Building2,
  CalendarDays,
  CheckCircle2,
  Clock,
  Loader2,
  MapPin,
  Search,
} from "lucide-react";
import { useCustomerAuth } from "@/lib/customer-auth-context";
import {
  customerApiClient,
  CustomerApiError,
  CustomerAvailableSlot,
  CustomerSiteVisit,
  PublicProjectCard,
} from "@/lib/customer-api-client";

type Step = "project" | "slot" | "review" | "done";

function todayIsoDate(): string {
  // Local-date (not UTC) so a customer browsing late at night doesn't get
  // pushed to tomorrow's date by a naive toISOString() call.
  const now = new Date();
  const offset = now.getTimezoneOffset();
  const local = new Date(now.getTime() - offset * 60000);
  return local.toISOString().slice(0, 10);
}

function formatSlotTime(iso: string): string {
  return new Date(iso).toLocaleTimeString("en-IN", { timeZone: "Asia/Kolkata", hour: "2-digit", minute: "2-digit" });
}

function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString("en-IN", { timeZone: "Asia/Kolkata", dateStyle: "medium", timeStyle: "short" });
}

function newIdempotencyKey(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return crypto.randomUUID();
  return `idem-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export default function BookSiteVisitPage() {
  const { customer, isLoading } = useCustomerAuth();
  const router = useRouter();

  const [step, setStep] = useState<Step>("project");

  const [search, setSearch] = useState("");
  const [projects, setProjects] = useState<PublicProjectCard[] | null>(null);
  const [projectsError, setProjectsError] = useState<string | null>(null);
  const [selectedProject, setSelectedProject] = useState<PublicProjectCard | null>(null);

  const [date, setDate] = useState(todayIsoDate());
  const [slots, setSlots] = useState<CustomerAvailableSlot[] | null>(null);
  const [slotsLoading, setSlotsLoading] = useState(false);
  const [slotsError, setSlotsError] = useState<string | null>(null);
  const [selectedSlot, setSelectedSlot] = useState<CustomerAvailableSlot | null>(null);
  const slotsRequestRef = useRef(0);

  const [idempotencyKey, setIdempotencyKey] = useState(() => newIdempotencyKey());
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [booking, setBooking] = useState<CustomerSiteVisit | null>(null);

  useEffect(() => {
    if (!isLoading && !customer) {
      router.replace("/customer/login?returnTo=/customer/visits/book");
    }
  }, [isLoading, customer, router]);

  const loadProjects = useCallback(async (searchTerm: string) => {
    setProjects(null);
    setProjectsError(null);
    try {
      const result = await customerApiClient.listPublishedProjects({ search: searchTerm || undefined, limit: 20 });
      setProjects(result.items);
    } catch (err) {
      setProjectsError(err instanceof CustomerApiError ? err.message : "Unable to load projects. Please try again.");
    }
  }, []);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- intentional data fetch on customer load
    if (customer && step === "project") loadProjects(search);
  }, [customer, step, search, loadProjects]);

  const loadSlots = useCallback(async () => {
    if (!selectedProject) return;
    // Only the latest request may update state: an older request (e.g. for
    // the previously selected date) can resolve after a newer one and would
    // otherwise show -- and let the buyer pick -- another day's slots.
    const requestId = ++slotsRequestRef.current;
    setSlots(null);
    setSlotsLoading(true);
    setSlotsError(null);
    setSelectedSlot(null);
    try {
      const result = await customerApiClient.getVisitAvailability(selectedProject.id, date);
      if (requestId === slotsRequestRef.current) setSlots(result.slots);
    } catch (err) {
      if (requestId === slotsRequestRef.current) {
        setSlotsError(err instanceof CustomerApiError ? err.message : "Unable to load available slots.");
      }
    } finally {
      if (requestId === slotsRequestRef.current) setSlotsLoading(false);
    }
  }, [selectedProject, date]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- intentional slot refetch on project/date change
    if (step === "slot") loadSlots();
  }, [step, loadSlots]);

  const handleConfirmBooking = async () => {
    if (!selectedProject || !selectedSlot || submitting) return;
    setSubmitting(true);
    setSubmitError(null);
    try {
      const result = await customerApiClient.createVisitBooking(
        { project_id: selectedProject.id, scheduled_start: selectedSlot.start_time, scheduled_end: selectedSlot.end_time },
        idempotencyKey
      );
      setBooking(result);
      setStep("done");
    } catch (err) {
      if (err instanceof CustomerApiError && (err.status === 409 || err.status === 422)) {
        setSubmitError(`${err.message} The selected time may no longer be available -- please choose another slot.`);
        setSelectedSlot(null);
        setIdempotencyKey(newIdempotencyKey());
        await loadSlots();
      } else {
        setSubmitError(err instanceof CustomerApiError ? err.message : "Failed to create booking. Please try again.");
      }
    } finally {
      setSubmitting(false);
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
    <div className="w-full max-w-2xl space-y-6">
      {step !== "done" && (
        <div>
          <Link href="/customer/visits" className="inline-flex items-center gap-1.5 text-sm text-[#737C76] hover:text-[#173B35] mb-3">
            <ArrowLeft className="w-3.5 h-3.5" />
            Back to my visits
          </Link>
          <h1 className="font-heading font-bold text-xl text-[#202B28]">Book a site visit</h1>
          <p className="text-sm text-[#737C76] mt-1">
            Step {step === "project" ? 1 : step === "slot" ? 2 : 3} of 3
          </p>
        </div>
      )}

      {/* Step 1: project selection */}
      {step === "project" && (
        <div className="bg-white rounded-xl border border-[#E5E5DE] shadow-xs p-6 space-y-4">
          <div className="relative">
            <Search className="w-4 h-4 text-[#9FAAA4] absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search published projects by name"
              className="w-full h-11 pl-10 pr-3 rounded-lg border border-[#E5E5DE] text-sm focus:outline-none focus:ring-2 focus:ring-[#315C50]"
            />
          </div>

          {projectsError && <p className="text-sm text-[#C34D4D]">{projectsError}</p>}

          {projects === null && !projectsError && (
            <div className="flex items-center justify-center py-10 text-sm text-[#737C76] gap-2">
              <Loader2 className="w-4 h-4 animate-spin" />
              Loading projects...
            </div>
          )}

          {projects !== null && projects.length === 0 && (
            <p className="text-sm text-[#737C76] text-center py-6">No published projects match your search.</p>
          )}

          {projects !== null && projects.length > 0 && (
            <div className="space-y-2 max-h-96 overflow-y-auto">
              {projects.map((project) => (
                <button
                  key={project.id}
                  onClick={() => {
                    setSelectedProject(project);
                    setStep("slot");
                  }}
                  className="w-full flex items-center gap-3 p-3 rounded-lg border border-[#E5E5DE] hover:border-[#315C50] hover:bg-[#F7F6F2] transition-colors text-left"
                >
                  <div className="w-10 h-10 rounded-lg bg-[#F0F1EC] flex items-center justify-center shrink-0">
                    <Building2 className="w-5 h-5 text-[#173B35]" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-semibold text-[#202B28] truncate">{project.name}</p>
                    {project.location && (
                      <p className="text-xs text-[#737C76] flex items-center gap-1 mt-0.5">
                        <MapPin className="w-3 h-3 shrink-0" />
                        {project.location}
                      </p>
                    )}
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Step 2: date + slot selection */}
      {step === "slot" && selectedProject && (
        <div className="bg-white rounded-xl border border-[#E5E5DE] shadow-xs p-6 space-y-5">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-xs text-[#737C76]">Selected project</p>
              <p className="text-sm font-semibold text-[#202B28]">{selectedProject.name}</p>
            </div>
            <button onClick={() => setStep("project")} className="text-xs font-semibold text-[#173B35] hover:underline">
              Change
            </button>
          </div>

          <div>
            <label className="block text-xs font-semibold text-[#202B28] mb-1.5 flex items-center gap-1.5">
              <CalendarDays className="w-3.5 h-3.5" /> Visit date
            </label>
            <input
              type="date"
              value={date}
              min={todayIsoDate()}
              onChange={(e) => setDate(e.target.value)}
              className="w-full h-10 px-3 rounded-lg border border-[#E5E5DE] text-sm focus:outline-none focus:ring-2 focus:ring-[#315C50]"
            />
          </div>

          <div>
            <p className="text-xs font-semibold text-[#202B28] mb-2 flex items-center gap-1.5">
              <Clock className="w-3.5 h-3.5" /> Available times (Asia/Kolkata)
            </p>
            {slotsLoading && (
              <div className="flex items-center gap-2 text-sm text-[#737C76] py-4">
                <Loader2 className="w-4 h-4 animate-spin" />
                Loading available slots...
              </div>
            )}
            {!slotsLoading && slotsError && <p className="text-sm text-[#C34D4D]">{slotsError}</p>}
            {!slotsLoading && !slotsError && slots && slots.length === 0 && (
              <p className="text-sm text-[#737C76] py-2">No slots are available on this date. Try another date.</p>
            )}
            {!slotsLoading && !slotsError && slots && slots.length > 0 && (
              <div className="flex flex-wrap gap-2">
                {slots.map((slot) => (
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
          </div>

          <button
            disabled={!selectedSlot}
            onClick={() => setStep("review")}
            className="w-full h-11 rounded-lg bg-[#173B35] hover:bg-[#1f4b43] text-white text-sm font-semibold disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            Continue
          </button>
        </div>
      )}

      {/* Step 3: review + confirm */}
      {step === "review" && selectedProject && selectedSlot && (
        <div className="bg-white rounded-xl border border-[#E5E5DE] shadow-xs p-6 space-y-5">
          <h2 className="font-heading font-bold text-base text-[#202B28]">Review your booking</h2>
          <dl className="grid grid-cols-1 gap-3 text-sm bg-[#F7F6F2] rounded-lg p-4">
            <div className="flex justify-between">
              <dt className="text-[#737C76]">Project</dt>
              <dd className="font-semibold text-[#202B28]">{selectedProject.name}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-[#737C76]">Date &amp; time</dt>
              <dd className="font-semibold text-[#202B28]">{formatDateTime(selectedSlot.start_time)}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-[#737C76]">Timezone</dt>
              <dd className="font-semibold text-[#202B28]">Asia/Kolkata (IST)</dd>
            </div>
          </dl>

          {submitError && (
            <div className="flex items-start gap-2 text-sm text-[#C34D4D]">
              <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
              <p>{submitError}</p>
            </div>
          )}

          <div className="flex gap-3">
            <button
              onClick={() => setStep("slot")}
              disabled={submitting}
              className="flex-1 h-11 rounded-lg border border-[#E5E5DE] text-sm font-semibold text-[#202B28] hover:bg-[#F0F1EC] transition-colors disabled:opacity-40"
            >
              Back
            </button>
            <button
              onClick={handleConfirmBooking}
              disabled={submitting}
              className="flex-1 h-11 rounded-lg bg-[#173B35] hover:bg-[#1f4b43] text-white text-sm font-semibold transition-colors disabled:opacity-60 flex items-center justify-center gap-2"
            >
              {submitting && <Loader2 className="w-4 h-4 animate-spin" />}
              Confirm booking
            </button>
          </div>
        </div>
      )}

      {/* Step 4: confirmation */}
      {step === "done" && booking && (
        <div className="bg-white rounded-xl border border-[#E5E5DE] shadow-xs p-8 text-center space-y-4">
          <CheckCircle2 className="w-10 h-10 text-[#27845B] mx-auto" />
          <h2 className="font-heading font-bold text-xl text-[#202B28]">Your site visit is booked</h2>
          <dl className="grid grid-cols-1 gap-3 text-sm bg-[#F7F6F2] rounded-lg p-4 text-left">
            <div className="flex justify-between">
              <dt className="text-[#737C76]">Project</dt>
              <dd className="font-semibold text-[#202B28]">{booking.project_name}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-[#737C76]">Date &amp; time</dt>
              <dd className="font-semibold text-[#202B28]">{formatDateTime(booking.scheduled_start)} (IST)</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-[#737C76]">Booking reference</dt>
              <dd className="font-semibold text-[#202B28]">{booking.booking_reference}</dd>
            </div>
          </dl>
          <p className="text-sm text-[#737C76]">
            We&apos;ll send you reminders before your visit. You can view, reschedule, or cancel this booking anytime
            from your visits page.
          </p>
          <div className="flex gap-3 justify-center">
            <Link
              href={`/customer/visits/${booking.id}`}
              className="h-10 px-4 rounded-lg bg-[#173B35] hover:bg-[#1f4b43] text-white text-sm font-semibold transition-colors inline-flex items-center"
            >
              View booking
            </Link>
            <Link
              href="/customer/visits"
              className="h-10 px-4 rounded-lg border border-[#E5E5DE] text-sm font-semibold text-[#202B28] hover:bg-[#F0F1EC] transition-colors inline-flex items-center"
            >
              My visits
            </Link>
          </div>
        </div>
      )}
    </div>
  );
}
