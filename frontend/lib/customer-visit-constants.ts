// Shared display constants for the customer site-visit booking pages
// (Feature 13), mirroring lib/customer-chat-constants.ts's pattern.
import { SiteVisitStatus, CustomerReminderStatusLabel } from "@/lib/customer-api-client";
import type { CustomerNotificationEvent, CustomerNotificationStatus } from "@/lib/customer-api-client";

export const VISIT_STATUS_LABEL: Record<SiteVisitStatus, string> = {
  CONFIRMED: "Confirmed",
  CANCELLED: "Cancelled",
  COMPLETED: "Visit Completed",
  NO_SHOW: "No-show",
};

export const VISIT_STATUS_BADGE_CLASS: Record<SiteVisitStatus, string> = {
  CONFIRMED: "bg-[#E9F5EF] text-[#27845B]",
  CANCELLED: "bg-[#FDF2F2] text-[#C34D4D]",
  COMPLETED: "bg-[#EDEFF8] text-[#3C4EA3]",
  NO_SHOW: "bg-[#FDF6EC] text-[#B9772F]",
};

export const REMINDER_STATUS_LABEL: Record<CustomerReminderStatusLabel, string> = {
  PENDING: "Scheduled",
  SIMULATED: "Sent (simulated)",
  SENT: "Sent",
  CANCELLED: "Cancelled",
};

// Customer notification history (Feature 14).

export const NOTIFICATION_EVENT_LABEL: Record<CustomerNotificationEvent, string> = {
  SITE_VISIT_BOOKED: "Booked",
  SITE_VISIT_RESCHEDULED: "Rescheduled",
  SITE_VISIT_CANCELLED: "Cancelled",
  SITE_VISIT_REMINDER_24H: "Reminder (24 hours)",
  SITE_VISIT_REMINDER_2H: "Reminder (2 hours)",
};

export const NOTIFICATION_STATUS_LABEL: Record<CustomerNotificationStatus, string> = {
  SENT: "Sent",
  SIMULATED: "Simulated",
  PENDING: "Pending",
  FAILED: "Failed",
  NOT_SENT: "Not sent",
};

export const NOTIFICATION_STATUS_BADGE_CLASS: Record<CustomerNotificationStatus, string> = {
  SENT: "bg-[#E9F5EF] text-[#27845B]",
  SIMULATED: "bg-[#EDEFF8] text-[#3C4EA3]",
  PENDING: "bg-[#FDF6EC] text-[#B9772F]",
  FAILED: "bg-[#FDF2F2] text-[#C34D4D]",
  NOT_SENT: "bg-[#F0F1EC] text-[#737C76]",
};
