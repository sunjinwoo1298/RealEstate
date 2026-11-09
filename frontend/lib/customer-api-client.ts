// Customer-facing API client, kept entirely separate from `lib/api-client.ts`
// (the staff client) per Feature 10's requirement that customer and staff API
// clients be logically separated. Never shares the staff access token.
//
// Feature 13 reuses the public-project *types* from lib/api-client.ts (no
// auth is required to browse published projects, and duplicating that shape
// here would drift from the single source of truth) while still routing
// every network call through this client, per that feature's "do not create
// a separate customer API client" instruction.
import type { PublicProjectCard, PublicProjectListResponse } from "@/lib/api-client";
import { withCrossTabLock } from "@/lib/cross-tab-lock";
export type { PublicProjectCard, PublicProjectListResponse };

export type CustomerAccountStatus = "PENDING_VERIFICATION" | "ACTIVE" | "SUSPENDED" | "DEACTIVATED";

export interface CustomerPublic {
  id: string;
  full_name: string;
  email: string;
  email_verified: boolean;
  phone: string | null;
  status: CustomerAccountStatus;
  lead_linked: boolean;
  created_at: string;
}

export interface CustomerLoginResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  customer: CustomerPublic;
}

export interface CustomerRefreshResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
}

export interface CustomerRegisterResponse {
  message: string;
  email: string;
}

export interface GenericMessageResponse {
  message: string;
}

export interface CustomerProfile {
  id: string;
  full_name: string;
  email: string;
  email_verified: boolean;
  phone: string | null;
  phone_verified: boolean;
  status: CustomerAccountStatus;
  lead_linked: boolean;
  created_at: string;
  profile_completeness: number;
}

export interface CustomerProfileUpdatePayload {
  full_name?: string;
  phone?: string;
}

export interface CustomerEnquirySummary {
  has_enquiry: boolean;
  enquiry_reference: string | null;
  project_id: string | null;
  project_name: string | null;
  configuration: string | null;
  enquiry_date: string | null;
  customer_status: string | null;
}

// Customer chat (Feature 12) -- mirrors the buyer-chat types in
// lib/api-client.ts, kept as a separate set of types here since the
// customer-facing API intentionally returns a slightly different shape
// (no lead_id, no message metadata).

export type ConversationStatus = "ACTIVE" | "CLOSED";
export type OwnershipStatus = "AI_ACTIVE" | "PENDING_ASSIGNMENT" | "HUMAN_ACTIVE" | "RESOLVED";
export type ConversationLanguage = "EN" | "HI" | "GU";
export type ConversationState = "DISCOVERY" | "QUALIFIED" | "VISIT_REQUESTED" | "VISIT_BOOKED";
export type SenderType = "BUYER" | "AI" | "STAFF" | "SYSTEM";
export type MessageType = "TEXT" | "SYSTEM_EVENT";
export type HandoffStatus = "PENDING" | "ASSIGNED" | "ACCEPTED" | "RESOLVED" | "CANCELLED";

export interface CustomerConversation {
  id: string;
  status: ConversationStatus;
  ownership_status: OwnershipStatus;
  language: ConversationLanguage;
  conversation_state: ConversationState;
  created_at: string;
  updated_at: string;
  last_message_at: string | null;
}

export interface CustomerConversationListItem extends CustomerConversation {
  last_message_preview: string | null;
  last_message_sender_type: SenderType | null;
}

export interface CustomerConversationListResponse {
  items: CustomerConversationListItem[];
  total: number;
}

export interface CustomerChatMessage {
  id: string;
  conversation_id: string;
  sender_type: SenderType;
  content: string;
  message_type: MessageType;
  created_at: string;
}

export interface CustomerMessageListResponse {
  items: CustomerChatMessage[];
  total: number;
}

export interface CustomerHandoffStatus {
  status: HandoffStatus;
  created_at: string;
}

// Customer site-visit booking (Feature 13) -- reuses the public project
// discovery types (project selection) but defines its own booking/slot
// shapes, since the customer-facing API intentionally differs from both the
// staff booking schema (lib/api-client.ts SiteVisitDetail) and the
// anonymous buyer-chat booking path.

export type SiteVisitStatus = "CONFIRMED" | "CANCELLED" | "COMPLETED" | "NO_SHOW";
export type ReminderType = "24H" | "2H";
export type CustomerReminderStatusLabel = "PENDING" | "SIMULATED" | "SENT" | "CANCELLED";

export interface CustomerAvailableSlot {
  start_time: string;
  end_time: string;
}

export interface CustomerAvailableSlotsResponse {
  project_id: string;
  date: string;
  display_timezone: string;
  slots: CustomerAvailableSlot[];
}

export interface CustomerReminderInfo {
  reminder_type: ReminderType;
  status: CustomerReminderStatusLabel;
}

export interface CustomerSiteVisit {
  id: string;
  project_id: string;
  project_name: string;
  project_location: string | null;
  project_rera_number: string | null;
  map_url: string | null;
  scheduled_start: string;
  scheduled_end: string;
  display_timezone: string;
  status: SiteVisitStatus;
  booking_reference: string;
  executive_full_name: string | null;
  reminder_24h: CustomerReminderInfo | null;
  reminder_2h: CustomerReminderInfo | null;
  created_at: string;
  updated_at: string;
}

export interface CustomerSiteVisitListResponse {
  items: CustomerSiteVisit[];
  total: number;
}

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

// Customer notifications (Feature 14). The API intentionally never returns
// the recipient address, provider errors or payload JSON.
export type CustomerNotificationEvent =
  | "SITE_VISIT_BOOKED"
  | "SITE_VISIT_RESCHEDULED"
  | "SITE_VISIT_CANCELLED"
  | "SITE_VISIT_REMINDER_24H"
  | "SITE_VISIT_REMINDER_2H";
export type CustomerNotificationStatus = "PENDING" | "SENT" | "SIMULATED" | "FAILED" | "NOT_SENT";

export interface CustomerNotification {
  id: string;
  event_type: CustomerNotificationEvent;
  channel: "EMAIL";
  status: CustomerNotificationStatus;
  project_name: string | null;
  visit_id: string | null;
  visit_start_time: string | null;
  created_at: string;
  sent_at: string | null;
}

export interface CustomerNotificationListResponse {
  items: CustomerNotification[];
  total: number;
  limit: number;
  offset: number;
}

export interface NotificationPreferences {
  transactional_email_enabled: boolean;
  marketing_email_enabled: boolean;
  email_verified: boolean;
}

export class CustomerApiError extends Error {
  status: number;
  code?: string;
  details?: unknown;

  constructor(message: string, status: number, code?: string, details?: unknown) {
    super(message);
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

type AccessTokenGetter = () => string | null;
type UnauthorizedHandler = () => void;

class CustomerApiClient {
  private baseUrl: string;
  private getAccessToken: AccessTokenGetter = () => null;
  private onUnauthorized: UnauthorizedHandler | null = null;
  private refreshPromise: Promise<CustomerRefreshResponse> | null = null;

  constructor(baseUrl: string) {
    this.baseUrl = baseUrl.replace(/\/+$/, "");
  }

  configureAuth(getAccessToken: AccessTokenGetter, onUnauthorized: UnauthorizedHandler) {
    this.getAccessToken = getAccessToken;
    this.onUnauthorized = onUnauthorized;
  }

  private async request<T>(
    endpoint: string,
    options: RequestInit = {},
    { retryOn401 = true, auth = true }: { retryOn401?: boolean; auth?: boolean } = {}
  ): Promise<T> {
    const url = `${this.baseUrl}${endpoint.startsWith("/") ? "" : "/"}${endpoint}`;
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
      ...(options.headers as Record<string, string> | undefined),
    };

    if (auth) {
      const token = this.getAccessToken();
      if (token) headers["Authorization"] = `Bearer ${token}`;
    }

    const res = await fetch(url, { ...options, headers, credentials: "include" });

    if (res.status === 401 && auth && retryOn401) {
      const newToken = await this.refreshAccessToken();
      if (newToken) {
        return this.request<T>(endpoint, options, { retryOn401: false, auth });
      }
      this.onUnauthorized?.();
    }

    if (res.status === 204) {
      return undefined as T;
    }

    if (!res.ok) {
      const errorBody = await res.json().catch(() => ({}));
      throw new CustomerApiError(
        errorBody?.error?.message || `Request failed with status ${res.status}: ${res.statusText}`,
        res.status,
        errorBody?.error?.code,
        errorBody?.error?.details
      );
    }

    return res.json() as Promise<T>;
  }

  /**
   * Single in-flight refresh shared by the provider's silent refresh on mount
   * and the 401-retry path. Refresh tokens rotate, and reusing one revokes the
   * whole token family, so concurrent refreshes must never both hit the API.
   */
  private refreshOnce(): Promise<CustomerRefreshResponse> {
    if (!this.refreshPromise) {
      // Also serialised across tabs: the refresh cookie is shared browser-wide.
      this.refreshPromise = withCrossTabLock("estateflow-customer-refresh", () =>
        this.request<CustomerRefreshResponse>(
          "/customer-auth/refresh",
          { method: "POST" },
          { retryOn401: false, auth: false }
        )
      ).finally(() => {
        this.refreshPromise = null;
      });
    }
    return this.refreshPromise;
  }

  private async refreshAccessToken(): Promise<string | null> {
    return this.refreshOnce()
      .then((data) => data.access_token)
      .catch(() => null);
  }

  async register(payload: {
    full_name: string;
    email: string;
    password: string;
    password_confirmation: string;
    phone?: string;
    accepted_privacy_policy: boolean;
    marketing_consent: boolean;
  }): Promise<CustomerRegisterResponse> {
    return this.request<CustomerRegisterResponse>(
      "/customer-auth/register",
      { method: "POST", body: JSON.stringify(payload) },
      { auth: false, retryOn401: false }
    );
  }

  async verifyEmail(token: string): Promise<CustomerPublic> {
    return this.request<CustomerPublic>(
      "/customer-auth/verify-email",
      { method: "POST", body: JSON.stringify({ token }) },
      { auth: false, retryOn401: false }
    );
  }

  async resendVerification(email: string): Promise<GenericMessageResponse> {
    return this.request<GenericMessageResponse>(
      "/customer-auth/resend-verification",
      { method: "POST", body: JSON.stringify({ email }) },
      { auth: false, retryOn401: false }
    );
  }

  async login(email: string, password: string): Promise<CustomerLoginResponse> {
    return this.request<CustomerLoginResponse>(
      "/customer-auth/login",
      { method: "POST", body: JSON.stringify({ email, password }) },
      { auth: false, retryOn401: false }
    );
  }

  async refresh(): Promise<CustomerRefreshResponse> {
    return this.refreshOnce();
  }

  async logout(): Promise<void> {
    await this.request<void>(
      "/customer-auth/logout",
      { method: "POST" },
      { auth: false, retryOn401: false }
    );
  }

  async getMe(): Promise<CustomerPublic> {
    return this.request<CustomerPublic>("/customer-auth/me", { method: "GET" });
  }

  async forgotPassword(email: string): Promise<GenericMessageResponse> {
    return this.request<GenericMessageResponse>(
      "/customer-auth/forgot-password",
      { method: "POST", body: JSON.stringify({ email }) },
      { auth: false, retryOn401: false }
    );
  }

  async resetPassword(
    token: string,
    newPassword: string,
    newPasswordConfirmation: string
  ): Promise<GenericMessageResponse> {
    return this.request<GenericMessageResponse>(
      "/customer-auth/reset-password",
      {
        method: "POST",
        body: JSON.stringify({
          token,
          new_password: newPassword,
          new_password_confirmation: newPasswordConfirmation,
        }),
      },
      { auth: false, retryOn401: false }
    );
  }

  async getProfile(): Promise<CustomerProfile> {
    return this.request<CustomerProfile>("/customer/me", { method: "GET" });
  }

  async updateProfile(payload: CustomerProfileUpdatePayload): Promise<CustomerProfile> {
    return this.request<CustomerProfile>("/customer/me", {
      method: "PATCH",
      body: JSON.stringify(payload),
    });
  }

  async getEnquiry(): Promise<CustomerEnquirySummary> {
    return this.request<CustomerEnquirySummary>("/customer/me/enquiry", { method: "GET" });
  }

  async changePassword(
    currentPassword: string,
    newPassword: string,
    confirmNewPassword: string
  ): Promise<GenericMessageResponse> {
    return this.request<GenericMessageResponse>("/customer/me/change-password", {
      method: "POST",
      body: JSON.stringify({
        current_password: currentPassword,
        new_password: newPassword,
        confirm_new_password: confirmNewPassword,
      }),
    });
  }

  async createConversation(): Promise<CustomerConversation> {
    return this.request<CustomerConversation>("/customer/conversations", { method: "POST" });
  }

  async listConversations(params?: {
    conversation_state?: ConversationState;
    limit?: number;
    offset?: number;
  }): Promise<CustomerConversationListResponse> {
    const query = new URLSearchParams();
    if (params?.conversation_state) query.set("conversation_state", params.conversation_state);
    if (params?.limit) query.set("limit", String(params.limit));
    if (params?.offset) query.set("offset", String(params.offset));
    const qs = query.toString();
    return this.request<CustomerConversationListResponse>(`/customer/conversations${qs ? `?${qs}` : ""}`, {
      method: "GET",
    });
  }

  async getConversation(conversationId: string): Promise<CustomerConversation> {
    return this.request<CustomerConversation>(`/customer/conversations/${conversationId}`, { method: "GET" });
  }

  async getConversationMessages(
    conversationId: string,
    params?: { limit?: number; offset?: number }
  ): Promise<CustomerMessageListResponse> {
    const query = new URLSearchParams();
    if (params?.limit) query.set("limit", String(params.limit));
    if (params?.offset) query.set("offset", String(params.offset));
    const qs = query.toString();
    return this.request<CustomerMessageListResponse>(
      `/customer/conversations/${conversationId}/messages${qs ? `?${qs}` : ""}`,
      { method: "GET" }
    );
  }

  async sendConversationMessage(conversationId: string, content: string): Promise<CustomerChatMessage> {
    return this.request<CustomerChatMessage>(`/customer/conversations/${conversationId}/messages`, {
      method: "POST",
      body: JSON.stringify({ content }),
    });
  }

  async requestConversationHandoff(conversationId: string): Promise<CustomerHandoffStatus> {
    return this.request<CustomerHandoffStatus>(`/customer/conversations/${conversationId}/handoff`, {
      method: "POST",
    });
  }

  // --- Site-visit booking (Feature 13) ---

  // Published-project browsing reuses the existing unauthenticated public
  // endpoint (Feature 09) -- routed through this client, not a second one.
  async listPublishedProjects(params: {
    search?: string;
    location?: string;
    limit?: number;
    offset?: number;
  } = {}): Promise<PublicProjectListResponse> {
    const query = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== "") query.set(key, String(value));
    });
    const qs = query.toString();
    return this.request<PublicProjectListResponse>(
      `/public/projects${qs ? `?${qs}` : ""}`,
      { method: "GET" },
      { auth: false, retryOn401: false }
    );
  }

  async getVisitAvailability(projectId: string, date: string): Promise<CustomerAvailableSlotsResponse> {
    const query = new URLSearchParams({ project_id: projectId, date });
    return this.request<CustomerAvailableSlotsResponse>(`/customer/visits/availability?${query.toString()}`, {
      method: "GET",
    });
  }

  async createVisitBooking(
    payload: { project_id: string; scheduled_start: string; scheduled_end?: string },
    idempotencyKey: string
  ): Promise<CustomerSiteVisit> {
    return this.request<CustomerSiteVisit>("/customer/visits", {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
      body: JSON.stringify(payload),
    });
  }

  async listVisits(params?: {
    status?: SiteVisitStatus;
    upcoming?: boolean;
    limit?: number;
    offset?: number;
  }): Promise<CustomerSiteVisitListResponse> {
    const query = new URLSearchParams();
    if (params?.status) query.set("status", params.status);
    if (params?.upcoming !== undefined) query.set("upcoming", String(params.upcoming));
    if (params?.limit) query.set("limit", String(params.limit));
    if (params?.offset) query.set("offset", String(params.offset));
    const qs = query.toString();
    return this.request<CustomerSiteVisitListResponse>(`/customer/visits${qs ? `?${qs}` : ""}`, { method: "GET" });
  }

  async getVisit(visitId: string): Promise<CustomerSiteVisit> {
    return this.request<CustomerSiteVisit>(`/customer/visits/${visitId}`, { method: "GET" });
  }

  async rescheduleVisit(
    visitId: string,
    payload: { scheduled_start: string; scheduled_end?: string }
  ): Promise<CustomerSiteVisit> {
    return this.request<CustomerSiteVisit>(`/customer/visits/${visitId}/reschedule`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    });
  }

  async cancelVisit(visitId: string): Promise<CustomerSiteVisit> {
    return this.request<CustomerSiteVisit>(`/customer/visits/${visitId}/cancel`, { method: "POST" });
  }

  // --- Notifications (Feature 14) ---

  async listNotifications(params?: { limit?: number; offset?: number }): Promise<CustomerNotificationListResponse> {
    const query = new URLSearchParams();
    if (params?.limit) query.set("limit", String(params.limit));
    if (params?.offset) query.set("offset", String(params.offset));
    const qs = query.toString();
    return this.request<CustomerNotificationListResponse>(`/customer/notifications${qs ? `?${qs}` : ""}`, {
      method: "GET",
    });
  }

  async getNotificationPreferences(): Promise<NotificationPreferences> {
    return this.request<NotificationPreferences>("/customer/notification-preferences", { method: "GET" });
  }

  async updateNotificationPreferences(transactionalEmailEnabled: boolean): Promise<NotificationPreferences> {
    return this.request<NotificationPreferences>("/customer/notification-preferences", {
      method: "PATCH",
      body: JSON.stringify({ transactional_email_enabled: transactionalEmailEnabled }),
    });
  }
}

export const customerApiClient = new CustomerApiClient(API_BASE_URL);
