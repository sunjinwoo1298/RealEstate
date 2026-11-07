"use client";

import React, { useEffect, useState } from "react";
import { CalendarDays, Clock, Plus, X } from "lucide-react";
import {
  apiClient,
  ApiError,
  AvailableSlotPublic,
  ProjectPublic,
  SiteVisitPublic,
  SiteVisitStatus,
} from "@/lib/api-client";

const STATUS_BADGE: Record<SiteVisitStatus, string> = {
  CONFIRMED: "bg-[#E9F5EF] text-[#27845B]",
  CANCELLED: "bg-[#FDF2F2] text-[#C34D4D]",
  COMPLETED: "bg-[#EDEFF8] text-[#3C4EA3]",
  NO_SHOW: "bg-[#FDF6EC] text-[#B9772F]",
};

function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString("en-IN", {
    timeZone: "Asia/Kolkata",
    dateStyle: "medium",
    timeStyle: "short",
  });
}

export default function SiteVisitsPage() {
  const [visits, setVisits] = useState<SiteVisitPublic[]>([]);
  const [projects, setProjects] = useState<ProjectPublic[]>([]);
  const [statusFilter, setStatusFilter] = useState<SiteVisitStatus | "">("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [showNewBooking, setShowNewBooking] = useState(false);
  const [bookingProjectId, setBookingProjectId] = useState("");
  const [bookingLeadId, setBookingLeadId] = useState("");
  const [bookingDate, setBookingDate] = useState("");
  const [slots, setSlots] = useState<AvailableSlotPublic[]>([]);
  const [slotsLoading, setSlotsLoading] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const loadVisits = async () => {
    setLoading(true);
    try {
      const data = await apiClient.listBookings({ status: statusFilter || undefined, limit: 50 });
      setVisits(data.items);
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load site visits.");
    } finally {
      setLoading(false);
    }
  };

  const loadProjects = async () => {
    try {
      const data = await apiClient.listProjects({});
      setProjects(data.items);
    } catch {
      // Project list is only needed for the new-booking form; leave it empty on failure.
    }
  };

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- intentional data fetch on mount/filter change
    loadVisits();
  }, [statusFilter]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- intentional data fetch on mount
    loadProjects();
  }, []);

  const loadSlots = async () => {
    if (!bookingProjectId || !bookingDate) return;
    setSlotsLoading(true);
    setFormError(null);
    try {
      const data = await apiClient.getAvailableSlots({ project_id: bookingProjectId, date: bookingDate });
      setSlots(data.slots);
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : "Failed to load available slots.");
      setSlots([]);
    } finally {
      setSlotsLoading(false);
    }
  };

  useEffect(() => {
    if (bookingProjectId && bookingDate) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- intentional slot refetch on project/date change
      loadSlots();
    } else {
      setSlots([]);
    }
  }, [bookingProjectId, bookingDate]);

  const handleBookSlot = async (slot: AvailableSlotPublic) => {
    if (!bookingLeadId) {
      setFormError("Enter the lead ID this visit is for.");
      return;
    }
    setSubmitting(true);
    setFormError(null);
    try {
      await apiClient.createBooking({
        lead_id: bookingLeadId,
        project_id: bookingProjectId,
        start_time: slot.start_time,
      });
      setShowNewBooking(false);
      setBookingLeadId("");
      setSlots([]);
      await loadVisits();
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : "Failed to create booking.");
    } finally {
      setSubmitting(false);
    }
  };

  const handleCancel = async (visitId: string) => {
    try {
      await apiClient.cancelBooking(visitId);
      await loadVisits();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to cancel visit.");
    }
  };

  const handleAttendance = async (visitId: string, outcome: "COMPLETED" | "NO_SHOW") => {
    try {
      await apiClient.recordAttendance(visitId, outcome);
      await loadVisits();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to record attendance.");
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold font-heading text-[#202B28] tracking-tight">Site Visits</h1>
          <p className="text-sm text-[#737C76] mt-1">
            Executive-assigned, concurrency-safe site-visit bookings.
          </p>
        </div>
        <button
          onClick={() => setShowNewBooking((v) => !v)}
          className="h-10 px-4 rounded-lg bg-[#173B35] hover:bg-[#1f4b43] text-white text-sm font-semibold flex items-center gap-2 transition-colors"
        >
          {showNewBooking ? <X className="w-4 h-4" /> : <Plus className="w-4 h-4" />}
          {showNewBooking ? "Close" : "New Booking"}
        </button>
      </div>

      {showNewBooking && (
        <div className="bg-white rounded-xl border border-[#E5E5DE] shadow-xs p-6 space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div>
              <label className="block text-xs font-semibold text-[#202B28] mb-1.5">Project</label>
              <select
                value={bookingProjectId}
                onChange={(e) => setBookingProjectId(e.target.value)}
                className="w-full h-10 px-3 rounded-lg border border-[#E5E5DE] text-sm bg-white focus:outline-none focus:ring-2 focus:ring-[#315C50]"
              >
                <option value="">Select a project</option>
                {projects.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-xs font-semibold text-[#202B28] mb-1.5">Lead ID</label>
              <input
                value={bookingLeadId}
                onChange={(e) => setBookingLeadId(e.target.value)}
                placeholder="Lead UUID"
                className="w-full h-10 px-3 rounded-lg border border-[#E5E5DE] text-sm focus:outline-none focus:ring-2 focus:ring-[#315C50]"
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-[#202B28] mb-1.5">Date</label>
              <input
                type="date"
                value={bookingDate}
                onChange={(e) => setBookingDate(e.target.value)}
                className="w-full h-10 px-3 rounded-lg border border-[#E5E5DE] text-sm focus:outline-none focus:ring-2 focus:ring-[#315C50]"
              />
            </div>
          </div>

          {formError && <p className="text-sm text-[#C34D4D]">{formError}</p>}

          <div>
            <p className="text-xs font-semibold text-[#202B28] mb-2 flex items-center gap-1.5">
              <Clock className="w-3.5 h-3.5" /> Available slots (Asia/Kolkata)
            </p>
            {slotsLoading ? (
              <p className="text-sm text-[#737C76]">Loading slots...</p>
            ) : slots.length === 0 ? (
              <p className="text-sm text-[#737C76]">
                {bookingProjectId && bookingDate ? "No slots available for this date." : "Choose a project and date."}
              </p>
            ) : (
              <div className="flex flex-wrap gap-2">
                {slots.map((slot) => (
                  <button
                    key={slot.start_time}
                    disabled={submitting}
                    onClick={() => handleBookSlot(slot)}
                    className="h-9 px-3 rounded-lg border border-[#315C50] text-[#173B35] text-xs font-semibold hover:bg-[#E9F5EF] disabled:opacity-60 transition-colors"
                  >
                    {new Date(slot.start_time).toLocaleTimeString("en-IN", {
                      timeZone: "Asia/Kolkata",
                      hour: "2-digit",
                      minute: "2-digit",
                    })}
                    <span className="ml-1 text-[#737C76]">({slot.available_executive_count} free)</span>
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      <div className="bg-white rounded-xl border border-[#E5E5DE] shadow-xs p-4 flex items-center gap-3">
        <label className="text-xs font-semibold text-[#202B28]">Status:</label>
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value as SiteVisitStatus | "")}
          className="h-10 px-3 rounded-lg border border-[#E5E5DE] text-sm bg-white focus:outline-none focus:ring-2 focus:ring-[#315C50]"
        >
          <option value="">All</option>
          <option value="CONFIRMED">Confirmed</option>
          <option value="COMPLETED">Completed</option>
          <option value="NO_SHOW">No-show</option>
          <option value="CANCELLED">Cancelled</option>
        </select>
      </div>

      <div className="bg-white rounded-xl border border-[#E5E5DE] shadow-xs overflow-hidden">
        <div className="px-6 py-4 border-b border-[#E5E5DE] flex items-center gap-2">
          <CalendarDays className="w-4 h-4 text-[#173B35]" />
          <h2 className="text-sm font-semibold text-[#202B28]">Bookings</h2>
        </div>

        {error && <p className="px-6 py-4 text-sm text-[#C34D4D]">{error}</p>}

        {loading ? (
          <div className="px-6 py-8 text-center text-sm text-[#737C76]">Loading...</div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs font-semibold text-[#737C76] uppercase tracking-wider border-b border-[#E5E5DE]">
                <th className="px-6 py-3">Reference</th>
                <th className="px-6 py-3">Start (IST)</th>
                <th className="px-6 py-3">Status</th>
                <th className="px-6 py-3 text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {visits.map((visit) => (
                <tr key={visit.id} className="border-b border-[#F0F1EC] last:border-0">
                  <td className="px-6 py-3 font-medium text-[#202B28]">{visit.booking_reference}</td>
                  <td className="px-6 py-3 text-[#737C76]">{formatDateTime(visit.start_time)}</td>
                  <td className="px-6 py-3">
                    <span className={`text-xs font-semibold px-2 py-1 rounded-md ${STATUS_BADGE[visit.status]}`}>
                      {visit.status}
                    </span>
                  </td>
                  <td className="px-6 py-3 text-right space-x-3">
                    {visit.status === "CONFIRMED" && (
                      <>
                        <button
                          onClick={() => handleAttendance(visit.id, "COMPLETED")}
                          className="text-xs font-semibold text-[#27845B] hover:underline"
                        >
                          Mark Completed
                        </button>
                        <button
                          onClick={() => handleAttendance(visit.id, "NO_SHOW")}
                          className="text-xs font-semibold text-[#B9772F] hover:underline"
                        >
                          No-show
                        </button>
                        <button
                          onClick={() => handleCancel(visit.id)}
                          className="text-xs font-semibold text-[#C34D4D] hover:underline"
                        >
                          Cancel
                        </button>
                      </>
                    )}
                  </td>
                </tr>
              ))}
              {visits.length === 0 && (
                <tr>
                  <td colSpan={4} className="px-6 py-8 text-center text-sm text-[#737C76]">
                    No site visits found.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
