import { withCrossTabLock } from "@/lib/cross-tab-lock";

export interface DatabaseHealth {
  status: string;
  database: string;
  latency_ms?: number;
  error?: string | null;
}

export interface RedisHealth {
  status: string;
  message: string;
  url?: string | null;
}

export interface HealthResponse {
  status: "healthy" | "degraded" | "unhealthy";
  timestamp: string;
  app_name: string;
  environment: string;
  version: string;
  database: DatabaseHealth;
  redis: RedisHealth;
}

export type UserRole = "ADMIN" | "MANAGER" | "SALES_EXECUTIVE";

export interface UserPublic {
  id: string;
  email: string;
  full_name: string;
  role: UserRole;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  user: UserPublic;
}

export interface RefreshResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
}

export interface UserListResponse {
  items: UserPublic[];
  total: number;
}

export type SourceType =
  | "WEBSITE"
  | "PROPERTY_PORTAL"
  | "SOCIAL_AD"
  | "HOARDING"
  | "MANUAL"
  | "CSV_IMPORT";

export type LeadStatus =
  | "NEW"
  | "AI_CONTACTED"
  | "QUALIFIED"
  | "VISIT_REQUESTED"
  | "VISIT_BOOKED"
  | "VISIT_COMPLETED"
  | "CONVERTED"
  | "LOST"
  | "OPTED_OUT";

export type ConsentStatus = "GRANTED" | "DECLINED" | "NOT_RECORDED";

export type DuplicateReviewStatus = "PENDING_REVIEW" | "CONFIRMED_DUPLICATE" | "REJECTED";

export interface LeadListItem {
  id: string;
  full_name: string;
  normalized_phone: string | null;
  normalized_email: string | null;
  preferred_language: string | null;
  lead_status: LeadStatus;
  assigned_executive_id: string | null;
  consent_status: ConsentStatus;
  created_at: string;
  updated_at: string;
  source_count: number;
  latest_source_type: SourceType | null;
}

export interface LeadListResponse {
  items: LeadListItem[];
  total: number;
  new_count: number;
}

export interface LeadSourcePublic {
  id: string;
  source_type: SourceType;
  external_lead_id: string | null;
  campaign_name: string | null;
  submitted_at: string;
  created_at: string;
}

export interface LeadDetail extends LeadListItem {
  sources: LeadSourcePublic[];
}

export interface IngestionResponse {
  lead_id: string;
  lead_source_id: string;
  created_new_lead: boolean;
  match_reason: string;
  idempotent_replay: boolean;
}

export interface CsvImportRowResult {
  row_number: number;
  status: string;
  message?: string | null;
  lead_id?: string | null;
}

export interface CsvImportResponse {
  total_rows: number;
  created: number;
  matched: number;
  failed: number;
  results: CsvImportRowResult[];
}

export interface PotentialDuplicatePublic {
  id: string;
  new_lead_id: string;
  existing_lead_id: string;
  match_reason: string;
  similarity_score: number | null;
  status: DuplicateReviewStatus;
  reviewed_by_id: string | null;
  reviewed_at: string | null;
  created_at: string;
  new_lead: LeadListItem | null;
  existing_lead: LeadListItem | null;
}

export interface PotentialDuplicateListResponse {
  items: PotentialDuplicatePublic[];
  total: number;
}

export type ConversationLanguage = "EN" | "HI" | "GU";
export type ConversationChannel = "WEB_CHAT";
export type ConversationStatus = "ACTIVE" | "CLOSED";
export type OwnershipStatus = "AI_ACTIVE" | "PENDING_ASSIGNMENT" | "HUMAN_ACTIVE" | "RESOLVED";
export type ConversationState = "DISCOVERY" | "QUALIFIED" | "VISIT_REQUESTED" | "VISIT_BOOKED";
export type SenderType = "BUYER" | "AI" | "STAFF" | "SYSTEM";
export type MessageType = "TEXT" | "SYSTEM_EVENT";

export interface ConversationPublic {
  id: string;
  lead_id: string;
  channel: ConversationChannel;
  status: ConversationStatus;
  ownership_status: OwnershipStatus;
  language: ConversationLanguage;
  conversation_state: ConversationState;
  created_at: string;
  updated_at: string;
  last_message_at: string | null;
}

export interface ConversationListItem extends ConversationPublic {
  lead_full_name: string;
  lead_normalized_phone: string | null;
}

export interface ConversationListResponse {
  items: ConversationListItem[];
  total: number;
}

export interface MessagePublic {
  id: string;
  conversation_id: string;
  sender_type: SenderType;
  sender_id: string | null;
  content: string;
  message_type: MessageType;
  metadata: Record<string, unknown> | null;
  created_at: string;
}

export interface MessageListResponse {
  items: MessagePublic[];
  total: number;
}

// --- AI qualification & knowledge (Feature 04) ---

export type ProjectVisibility = "DRAFT" | "PUBLISHED" | "ARCHIVED";

export interface ProjectPublic {
  id: string;
  name: string;
  description: string | null;
  location: string | null;
  is_active: boolean;
  visibility_status: ProjectVisibility;
  is_featured: boolean;
  configurations: string[] | null;
  amenities: string[] | null;
  images: string[] | null;
  starting_price_label: string | null;
  price_display_approved: boolean;
  rera_number: string | null;
  floor_plan_url: string | null;
  created_at: string;
  updated_at: string;
}

export interface ProjectListResponse {
  items: ProjectPublic[];
  total: number;
}

// --- Public website / project discovery (Feature 09) ---

export interface PublicProjectCard {
  id: string;
  name: string;
  location: string | null;
  description: string | null;
  configurations: string[];
  primary_image: string | null;
  starting_price_label: string | null;
  is_featured: boolean;
}

export interface PublicProjectDetail extends PublicProjectCard {
  amenities: string[];
  images: string[];
  rera_number: string | null;
  floor_plan_url: string | null;
}

export interface PublicProjectListResponse {
  items: PublicProjectCard[];
  total: number;
}

export type ApprovalStatus = "DRAFT" | "APPROVED" | "ARCHIVED";

export interface KnowledgeDocumentPublic {
  id: string;
  project_id: string;
  title: string;
  version: number;
  approval_status: ApprovalStatus;
  source_filename: string | null;
  uploaded_by: string | null;
  approved_by: string | null;
  approved_at: string | null;
  created_at: string;
  updated_at: string;
  chunk_count: number;
}

export interface KnowledgeDocumentListResponse {
  items: KnowledgeDocumentPublic[];
  total: number;
}

// --- Availability & Booking Engine (Feature 05) ---

export interface AvailabilityRulePublic {
  id: string;
  executive_id: string;
  project_id: string | null;
  day_of_week: number;
  start_time: string;
  end_time: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface AvailabilityRuleListResponse {
  items: AvailabilityRulePublic[];
  total: number;
}

export interface BlockedPeriodPublic {
  id: string;
  executive_id: string;
  start_time: string;
  end_time: string;
  reason: string | null;
  created_at: string;
}

export interface ProjectVisitCapacityPublic {
  id: string;
  project_id: string;
  capacity: number;
  visit_duration_minutes: number;
  buffer_minutes: number;
}

export interface AvailableSlotPublic {
  start_time: string;
  end_time: string;
  available_executive_count: number;
}

export interface AvailableSlotsResponse {
  project_id: string;
  date: string;
  slots: AvailableSlotPublic[];
}

export type SiteVisitStatus = "CONFIRMED" | "CANCELLED" | "COMPLETED" | "NO_SHOW";

export interface SiteVisitPublic {
  id: string;
  lead_id: string;
  project_id: string;
  executive_id: string | null;
  start_time: string;
  end_time: string;
  status: SiteVisitStatus;
  booking_reference: string;
  created_at: string;
  updated_at: string;
}

export interface SiteVisitListResponse {
  items: SiteVisitPublic[];
  total: number;
}

// --- Reminders & Attendance (Feature 07) ---

export type ReminderType = "24H" | "2H";
export type ReminderStatus = "SCHEDULED" | "PROCESSING" | "SENT" | "SIMULATED" | "FAILED" | "CANCELLED" | "SKIPPED";

export interface VisitReminderPublic {
  id: string;
  site_visit_id: string;
  reminder_type: ReminderType;
  scheduled_at: string;
  status: ReminderStatus;
  attempt_count: number;
  last_attempt_at: string | null;
  sent_at: string | null;
  failure_reason: string | null;
  booking_version: number;
  created_at: string;
  updated_at: string;
}

export interface VisitReminderListResponse {
  items: VisitReminderPublic[];
  total: number;
}

export interface SiteVisitDetail extends SiteVisitPublic {
  lead_full_name: string;
  lead_normalized_phone: string | null;
  project_name: string;
  executive_full_name: string | null;
  reminder_24h: VisitReminderPublic | null;
  reminder_2h: VisitReminderPublic | null;
}

export interface SiteVisitDetailListResponse {
  items: SiteVisitDetail[];
  total: number;
}

// --- Human Handoff & Sales Workspace (Feature 06) ---

export type HandoffStatus = "PENDING" | "ASSIGNED" | "ACCEPTED" | "RESOLVED" | "CANCELLED";
export type HandoffReason = "BUYER_REQUEST" | "UNSUPPORTED_QUERY" | "LOW_CONFIDENCE" | "COMPLAINT" | "OTHER";
export type AssignmentStatus = "ASSIGNED" | "ACCEPTED" | "REJECTED" | "ENDED";

export interface HandoffPublic {
  id: string;
  conversation_id: string;
  lead_id: string;
  assigned_executive_id: string | null;
  status: HandoffStatus;
  reason: HandoffReason;
  summary: string | null;
  created_at: string;
  updated_at: string;
  resolved_at: string | null;
}

export interface HandoffListItem extends HandoffPublic {
  lead_full_name: string;
  lead_normalized_phone: string | null;
}

export interface HandoffListResponse {
  items: HandoffListItem[];
  total: number;
}

export interface ConversationAssignmentPublic {
  id: string;
  executive_id: string | null;
  assigned_by: string | null;
  status: AssignmentStatus;
  assigned_at: string;
  accepted_at: string | null;
  ended_at: string | null;
}

export interface HandoffQualificationSummary {
  project_id: string | null;
  configuration: string | null;
  budget_min: number | null;
  budget_max: number | null;
  purchase_purpose: string | null;
  preferred_visit_date: string | null;
}

export interface HandoffSiteVisitSummary {
  id: string;
  project_id: string;
  start_time: string;
  end_time: string;
  status: SiteVisitStatus;
  booking_reference: string;
}

export interface HandoffDetail extends HandoffPublic {
  lead_full_name: string;
  lead_normalized_phone: string | null;
  lead_normalized_email: string | null;
  lead_preferred_language: string | null;
  source_types: string[];
  qualification: HandoffQualificationSummary | null;
  site_visits: HandoffSiteVisitSummary[];
  assignments: ConversationAssignmentPublic[];
  conversation_ownership_status: OwnershipStatus;
}

// --- Analytics & Business Intelligence (Feature 08) ---

export type DateRangePreset =
  | "TODAY"
  | "LAST_7_DAYS"
  | "LAST_30_DAYS"
  | "THIS_MONTH"
  | "PREVIOUS_MONTH"
  | "CUSTOM";

export type VisitDateBasis = "BOOKING" | "VISIT";
export type ReminderDateBasis = "CREATED" | "EXECUTED";

export interface AnalyticsFilterParams {
  range?: DateRangePreset;
  date_from?: string;
  date_to?: string;
  project_id?: string;
  source_type?: SourceType;
  executive_id?: string;
}

function buildAnalyticsQuery(filters: AnalyticsFilterParams): string {
  const query = new URLSearchParams();
  if (filters.range) query.set("range", filters.range);
  if (filters.date_from) query.set("date_from", filters.date_from);
  if (filters.date_to) query.set("date_to", filters.date_to);
  if (filters.project_id) query.set("project_id", filters.project_id);
  if (filters.source_type) query.set("source_type", filters.source_type);
  if (filters.executive_id) query.set("executive_id", filters.executive_id);
  return query.toString();
}

export interface DateRangeEcho {
  preset: DateRangePreset;
  start_utc: string;
  end_utc: string;
}

export interface AppliedAnalyticsFilters {
  project_id: string | null;
  source_type: SourceType | null;
  executive_id: string | null;
}

export interface OverviewAnalytics {
  date_range: DateRangeEcho;
  filters: AppliedAnalyticsFilters;
  total_unique_leads: number;
  total_enquiry_records: number;
  median_response_time_seconds: number | null;
  qualification_rate_percent: number | null;
  site_visits_booked: number;
  attendance_rate_percent: number | null;
}

export interface LeadTrendPoint {
  date: string;
  unique_leads: number;
}

export interface LeadsBySource {
  source_type: SourceType;
  enquiry_count: number;
  unique_lead_count: number;
  percent_of_total_unique_leads: number | null;
}

export interface LeadsByProject {
  project_id: string | null;
  project_name: string | null;
  unique_lead_count: number;
}

export interface LeadAnalytics {
  date_range: DateRangeEcho;
  filters: AppliedAnalyticsFilters;
  total_unique_leads: number;
  total_enquiry_records: number;
  by_source: LeadsBySource[];
  by_project: LeadsByProject[];
  trend: LeadTrendPoint[];
}

export interface SourcePerformance extends LeadsBySource {
  by_project: LeadsByProject[];
}

export interface SourceAnalytics {
  date_range: DateRangeEcho;
  filters: AppliedAnalyticsFilters;
  sources: SourcePerformance[];
}

export interface ResponseTimeBucket {
  label: string;
  count: number;
}

export interface ResponseTimeAnalytics {
  date_range: DateRangeEcho;
  filters: AppliedAnalyticsFilters;
  leads_evaluated: number;
  leads_with_response: number;
  leads_without_response: number;
  leads_not_responded_within_48h: number;
  average_response_time_seconds: number | null;
  median_response_time_seconds: number | null;
  responded_within_2_minutes_percent: number | null;
  responded_within_5_minutes_percent: number | null;
  distribution_buckets: ResponseTimeBucket[];
}

export interface QualificationBreakdownItem {
  label: string;
  count: number;
}

export interface QualificationAnalytics {
  date_range: DateRangeEcho;
  filters: AppliedAnalyticsFilters;
  ai_handled_conversations: number;
  handed_off_conversations: number;
  handoff_rate_percent: number | null;
  leads_in_cohort: number;
  qualified_leads: number;
  qualification_completion_rate_percent: number | null;
  by_budget_range: QualificationBreakdownItem[];
  by_configuration: QualificationBreakdownItem[];
  by_purchase_purpose: QualificationBreakdownItem[];
  by_language: QualificationBreakdownItem[];
}

export interface FunnelStage {
  stage: string;
  lead_status_floor: LeadStatus | null;
  count: number;
  conversion_from_previous_percent: number | null;
}

export interface FunnelAnalytics {
  date_range: DateRangeEcho;
  filters: AppliedAnalyticsFilters;
  cohort_size: number;
  stages: FunnelStage[];
  excluded_lost: number;
  excluded_opted_out: number;
  note: string;
}

export interface VisitTrendPoint {
  date: string;
  count: number;
}

export interface ProjectVisitDistribution {
  project_id: string | null;
  project_name: string | null;
  count: number;
}

export interface SiteVisitAnalytics {
  date_range: DateRangeEcho;
  filters: AppliedAnalyticsFilters;
  date_basis: VisitDateBasis;
  total_booked: number;
  confirmed: number;
  completed: number;
  no_show: number;
  cancelled: number;
  attendance_rate_percent: number | null;
  no_show_rate_percent: number | null;
  trend: VisitTrendPoint[];
  by_project: ProjectVisitDistribution[];
}

export interface ExecutivePerformance {
  executive_id: string;
  executive_name: string;
  assigned_leads_current: number;
  leads_contacted: number;
  qualified_leads: number;
  conversations_assigned_current: number;
  conversations_assigned_historical: number;
  accepted_handoffs: number;
  site_visits_booked: number;
  site_visits_completed: number;
  no_show_count: number;
  attendance_rate_percent: number | null;
}

export interface ExecutiveAnalytics {
  date_range: DateRangeEcho;
  filters: AppliedAnalyticsFilters;
  executives: ExecutivePerformance[];
}

export interface ReminderStatusBreakdownItem {
  status: ReminderStatus;
  count: number;
}

export interface ReminderTrendPoint {
  date: string;
  count: number;
}

export interface ReminderAnalytics {
  date_range: DateRangeEcho;
  filters: AppliedAnalyticsFilters;
  date_basis: ReminderDateBasis;
  total_scheduled: number;
  sent: number;
  simulated: number;
  failed: number;
  cancelled: number;
  skipped: number;
  failure_rate_percent: number | null;
  status_breakdown: ReminderStatusBreakdownItem[];
  trend: ReminderTrendPoint[];
}

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

export class ApiError extends Error {
  status: number;
  code?: string;

  constructor(message: string, status: number, code?: string) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

type AccessTokenGetter = () => string | null;
type UnauthorizedHandler = () => void;

class ApiClient {
  private baseUrl: string;
  private getAccessToken: AccessTokenGetter = () => null;
  private onUnauthorized: UnauthorizedHandler | null = null;
  private refreshPromise: Promise<RefreshResponse> | null = null;

  constructor(baseUrl: string) {
    this.baseUrl = baseUrl.replace(/\/+$/, "");
  }

  /** Wires the client to the in-memory access token held by AuthProvider. */
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

    const res = await fetch(url, {
      ...options,
      headers,
      credentials: "include",
    });

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
      throw new ApiError(
        errorBody?.error?.message ||
          `API request failed with status ${res.status}: ${res.statusText}`,
        res.status,
        errorBody?.error?.code
      );
    }

    return res.json() as Promise<T>;
  }

  /**
   * Single in-flight refresh shared by every caller (the AuthProvider's
   * silent refresh on mount and the 401-retry path). Refresh tokens rotate
   * and the backend treats a second use of the same token as theft and
   * revokes every session, so two concurrent refreshes would log the user out.
   */
  private refreshOnce(): Promise<RefreshResponse> {
    if (!this.refreshPromise) {
      // Also serialised across tabs: the refresh cookie is shared browser-wide.
      this.refreshPromise = withCrossTabLock("estateflow-staff-refresh", () =>
        this.request<RefreshResponse>(
          "/auth/refresh",
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

  async getHealth(): Promise<HealthResponse> {
    return this.request<HealthResponse>("/health", { cache: "no-store" }, { auth: false });
  }

  async login(email: string, password: string): Promise<LoginResponse> {
    return this.request<LoginResponse>(
      "/auth/login",
      { method: "POST", body: JSON.stringify({ email, password }) },
      { auth: false, retryOn401: false }
    );
  }

  async refresh(): Promise<RefreshResponse> {
    return this.refreshOnce();
  }

  async logout(): Promise<void> {
    await this.request<void>(
      "/auth/logout",
      { method: "POST" },
      { auth: false, retryOn401: false }
    );
  }

  async getMe(): Promise<UserPublic> {
    return this.request<UserPublic>("/auth/me", { method: "GET" });
  }

  async listStaffUsers(): Promise<UserListResponse> {
    return this.request<UserListResponse>("/admin/users", { method: "GET" });
  }

  async createStaffUser(payload: {
    email: string;
    full_name: string;
    password: string;
    role: UserRole;
  }): Promise<UserPublic> {
    return this.request<UserPublic>("/admin/users", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  }

  async updateStaffUserStatus(userId: string, isActive: boolean): Promise<UserPublic> {
    return this.request<UserPublic>(`/admin/users/${userId}/status`, {
      method: "PATCH",
      body: JSON.stringify({ is_active: isActive }),
    });
  }

  async listLeads(params: {
    search?: string;
    source?: SourceType;
    lead_status?: LeadStatus;
    assigned_executive_id?: string;
    limit?: number;
    offset?: number;
  }): Promise<LeadListResponse> {
    const query = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== "") query.set(key, String(value));
    });
    return this.request<LeadListResponse>(`/leads?${query.toString()}`, { method: "GET" });
  }

  async getLead(leadId: string): Promise<LeadDetail> {
    return this.request<LeadDetail>(`/leads/${leadId}`, { method: "GET" });
  }

  async getLeadSources(leadId: string): Promise<LeadSourcePublic[]> {
    return this.request<LeadSourcePublic[]>(`/leads/${leadId}/sources`, { method: "GET" });
  }

  async updateLead(
    leadId: string,
    payload: Partial<{
      full_name: string;
      preferred_language: string;
      lead_status: LeadStatus;
      assigned_executive_id: string;
      consent_status: ConsentStatus;
    }>
  ): Promise<LeadDetail> {
    return this.request<LeadDetail>(`/leads/${leadId}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    });
  }

  async createManualLead(payload: {
    full_name: string;
    phone: string;
    email?: string;
    preferred_language?: string;
    campaign_name?: string;
    consent_status?: ConsentStatus;
    notes?: string;
  }): Promise<IngestionResponse> {
    return this.request<IngestionResponse>("/leads", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  }

  async importLeadsCsv(file: File): Promise<CsvImportResponse> {
    const token = this.getAccessToken();
    const formData = new FormData();
    formData.append("file", file);
    const res = await fetch(`${this.baseUrl}/leads/import`, {
      method: "POST",
      headers: token ? { Authorization: `Bearer ${token}` } : undefined,
      body: formData,
      credentials: "include",
    });
    if (!res.ok) {
      const errorBody = await res.json().catch(() => ({}));
      throw new ApiError(
        errorBody?.error?.message || `CSV import failed with status ${res.status}`,
        res.status,
        errorBody?.error?.code
      );
    }
    return res.json() as Promise<CsvImportResponse>;
  }

  async listPotentialDuplicates(reviewStatus?: DuplicateReviewStatus): Promise<PotentialDuplicateListResponse> {
    const query = new URLSearchParams();
    if (reviewStatus) query.set("review_status", reviewStatus);
    return this.request<PotentialDuplicateListResponse>(`/leads/duplicates?${query.toString()}`, { method: "GET" });
  }

  async reviewPotentialDuplicate(
    matchId: string,
    reviewStatus: "CONFIRMED_DUPLICATE" | "REJECTED"
  ): Promise<PotentialDuplicatePublic> {
    return this.request<PotentialDuplicatePublic>(`/leads/duplicates/${matchId}`, {
      method: "PATCH",
      body: JSON.stringify({ status: reviewStatus }),
    });
  }

  // --- Buyer chat (cookie-session authorized; never sends the staff bearer token) ---

  async createChatSession(payload: {
    full_name: string;
    phone: string;
    email?: string;
    preferred_language: ConversationLanguage;
    consent_given: boolean;
  }): Promise<ConversationPublic> {
    return this.request<ConversationPublic>(
      "/chat/sessions",
      { method: "POST", body: JSON.stringify(payload) },
      { auth: false, retryOn401: false }
    );
  }

  async getChatSession(): Promise<ConversationPublic> {
    return this.request<ConversationPublic>(
      "/chat/session",
      { method: "GET" },
      { auth: false, retryOn401: false }
    );
  }

  async logoutChatSession(): Promise<void> {
    await this.request<void>(
      "/chat/session/logout",
      { method: "POST" },
      { auth: false, retryOn401: false }
    );
  }

  async getChatConversation(conversationId: string): Promise<ConversationPublic> {
    return this.request<ConversationPublic>(
      `/chat/conversations/${conversationId}`,
      { method: "GET" },
      { auth: false, retryOn401: false }
    );
  }

  async getChatMessages(
    conversationId: string,
    params: { limit?: number; offset?: number } = {}
  ): Promise<MessageListResponse> {
    const query = new URLSearchParams();
    if (params.limit !== undefined) query.set("limit", String(params.limit));
    if (params.offset !== undefined) query.set("offset", String(params.offset));
    return this.request<MessageListResponse>(
      `/chat/conversations/${conversationId}/messages?${query.toString()}`,
      { method: "GET" },
      { auth: false, retryOn401: false }
    );
  }

  async sendChatMessage(conversationId: string, content: string): Promise<MessagePublic> {
    return this.request<MessagePublic>(
      `/chat/conversations/${conversationId}/messages`,
      { method: "POST", body: JSON.stringify({ content }) },
      { auth: false, retryOn401: false }
    );
  }

  // --- Staff conversation workspace ---

  async listConversations(params: {
    status?: ConversationStatus;
    limit?: number;
    offset?: number;
  } = {}): Promise<ConversationListResponse> {
    const query = new URLSearchParams();
    if (params.status) query.set("status", params.status);
    if (params.limit !== undefined) query.set("limit", String(params.limit));
    if (params.offset !== undefined) query.set("offset", String(params.offset));
    return this.request<ConversationListResponse>(`/conversations?${query.toString()}`, { method: "GET" });
  }

  async getConversation(conversationId: string): Promise<ConversationListItem> {
    return this.request<ConversationListItem>(`/conversations/${conversationId}`, { method: "GET" });
  }

  // --- Admin: projects & knowledge documents ---

  async listProjects(params: { is_active?: boolean; limit?: number; offset?: number } = {}): Promise<ProjectListResponse> {
    const query = new URLSearchParams();
    if (params.is_active !== undefined) query.set("is_active", String(params.is_active));
    if (params.limit !== undefined) query.set("limit", String(params.limit));
    if (params.offset !== undefined) query.set("offset", String(params.offset));
    return this.request<ProjectListResponse>(`/admin/projects?${query.toString()}`, { method: "GET" });
  }

  async createProject(payload: { name: string; description?: string; location?: string }): Promise<ProjectPublic> {
    return this.request<ProjectPublic>("/admin/projects", { method: "POST", body: JSON.stringify(payload) });
  }

  async updateProject(
    projectId: string,
    payload: Partial<{
      name: string;
      description: string;
      location: string;
      is_active: boolean;
      visibility_status: ProjectVisibility;
      is_featured: boolean;
      configurations: string[];
      amenities: string[];
      images: string[];
      starting_price_label: string;
      price_display_approved: boolean;
      rera_number: string;
      floor_plan_url: string;
    }>
  ): Promise<ProjectPublic> {
    return this.request<ProjectPublic>(`/admin/projects/${projectId}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    });
  }

  // --- Public website / project discovery (Feature 09, no auth) ---

  async getPublicProjects(params: {
    search?: string;
    location?: string;
    configuration?: string;
    limit?: number;
    offset?: number;
  } = {}): Promise<PublicProjectListResponse> {
    const query = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== "") query.set(key, String(value));
    });
    return this.request<PublicProjectListResponse>(
      `/public/projects?${query.toString()}`,
      { method: "GET" },
      { auth: false, retryOn401: false }
    );
  }

  async getFeaturedProjects(limit = 6): Promise<PublicProjectListResponse> {
    return this.request<PublicProjectListResponse>(
      `/public/projects/featured?limit=${limit}`,
      { method: "GET" },
      { auth: false, retryOn401: false }
    );
  }

  async getPublicProject(projectId: string): Promise<PublicProjectDetail> {
    return this.request<PublicProjectDetail>(
      `/public/projects/${projectId}`,
      { method: "GET" },
      { auth: false, retryOn401: false }
    );
  }

  async listKnowledgeDocuments(projectId?: string): Promise<KnowledgeDocumentListResponse> {
    const query = new URLSearchParams();
    if (projectId) query.set("project_id", projectId);
    return this.request<KnowledgeDocumentListResponse>(`/admin/knowledge/documents?${query.toString()}`, {
      method: "GET",
    });
  }

  async uploadKnowledgeDocument(payload: {
    project_id: string;
    title: string;
    file: File;
  }): Promise<KnowledgeDocumentPublic> {
    const token = this.getAccessToken();
    const formData = new FormData();
    formData.append("project_id", payload.project_id);
    formData.append("title", payload.title);
    formData.append("file", payload.file);
    const res = await fetch(`${this.baseUrl}/admin/knowledge/documents`, {
      method: "POST",
      headers: token ? { Authorization: `Bearer ${token}` } : undefined,
      body: formData,
      credentials: "include",
    });
    if (!res.ok) {
      const errorBody = await res.json().catch(() => ({}));
      throw new ApiError(
        errorBody?.error?.message || `Upload failed with status ${res.status}`,
        res.status,
        errorBody?.error?.code
      );
    }
    return res.json() as Promise<KnowledgeDocumentPublic>;
  }

  async approveKnowledgeDocument(documentId: string): Promise<KnowledgeDocumentPublic> {
    return this.request<KnowledgeDocumentPublic>(`/admin/knowledge/documents/${documentId}/approve`, {
      method: "POST",
    });
  }

  async archiveKnowledgeDocument(documentId: string): Promise<KnowledgeDocumentPublic> {
    return this.request<KnowledgeDocumentPublic>(`/admin/knowledge/documents/${documentId}/archive`, {
      method: "POST",
    });
  }

  // --- Availability (Feature 05) ---

  async getAvailableSlots(params: {
    project_id: string;
    date: string;
    preferred_start_time?: string;
    preferred_end_time?: string;
  }): Promise<AvailableSlotsResponse> {
    const query = new URLSearchParams();
    query.set("project_id", params.project_id);
    query.set("date", params.date);
    if (params.preferred_start_time) query.set("preferred_start_time", params.preferred_start_time);
    if (params.preferred_end_time) query.set("preferred_end_time", params.preferred_end_time);
    return this.request<AvailableSlotsResponse>(`/availability?${query.toString()}`, { method: "GET" });
  }

  async listAvailabilityRules(params: { executive_id?: string; project_id?: string } = {}): Promise<AvailabilityRuleListResponse> {
    const query = new URLSearchParams();
    if (params.executive_id) query.set("executive_id", params.executive_id);
    if (params.project_id) query.set("project_id", params.project_id);
    return this.request<AvailabilityRuleListResponse>(`/admin/availability-rules?${query.toString()}`, { method: "GET" });
  }

  async createAvailabilityRule(payload: {
    executive_id: string;
    project_id?: string;
    day_of_week: number;
    start_time: string;
    end_time: string;
    is_active?: boolean;
  }): Promise<AvailabilityRulePublic> {
    return this.request<AvailabilityRulePublic>("/admin/availability-rules", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  }

  async deleteAvailabilityRule(ruleId: string): Promise<void> {
    await this.request<void>(`/admin/availability-rules/${ruleId}`, { method: "DELETE" });
  }

  async listBlockedPeriods(executiveId?: string): Promise<BlockedPeriodPublic[]> {
    const query = new URLSearchParams();
    if (executiveId) query.set("executive_id", executiveId);
    return this.request<BlockedPeriodPublic[]>(`/admin/blocked-periods?${query.toString()}`, { method: "GET" });
  }

  async createBlockedPeriod(payload: {
    executive_id: string;
    start_time: string;
    end_time: string;
    reason?: string;
  }): Promise<BlockedPeriodPublic> {
    return this.request<BlockedPeriodPublic>("/admin/blocked-periods", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  }

  async deleteBlockedPeriod(blockedPeriodId: string): Promise<void> {
    await this.request<void>(`/admin/blocked-periods/${blockedPeriodId}`, { method: "DELETE" });
  }

  async getVisitCapacity(projectId: string): Promise<ProjectVisitCapacityPublic> {
    return this.request<ProjectVisitCapacityPublic>(`/admin/visit-capacity/${projectId}`, { method: "GET" });
  }

  async upsertVisitCapacity(payload: {
    project_id: string;
    capacity: number;
    visit_duration_minutes: number;
    buffer_minutes: number;
  }): Promise<ProjectVisitCapacityPublic> {
    return this.request<ProjectVisitCapacityPublic>("/admin/visit-capacity", {
      method: "PUT",
      body: JSON.stringify(payload),
    });
  }

  // --- Site-visit bookings (Feature 05) ---

  async listBookings(params: {
    project_id?: string;
    executive_id?: string;
    status?: SiteVisitStatus;
    limit?: number;
    offset?: number;
  } = {}): Promise<SiteVisitDetailListResponse> {
    const query = new URLSearchParams();
    if (params.project_id) query.set("project_id", params.project_id);
    if (params.executive_id) query.set("executive_id", params.executive_id);
    if (params.status) query.set("status", params.status);
    if (params.limit !== undefined) query.set("limit", String(params.limit));
    if (params.offset !== undefined) query.set("offset", String(params.offset));
    return this.request<SiteVisitDetailListResponse>(`/bookings?${query.toString()}`, { method: "GET" });
  }

  async getBooking(bookingId: string): Promise<SiteVisitDetail> {
    return this.request<SiteVisitDetail>(`/bookings/${bookingId}`, { method: "GET" });
  }

  async getBookingReminders(bookingId: string): Promise<VisitReminderListResponse> {
    return this.request<VisitReminderListResponse>(`/bookings/${bookingId}/reminders`, { method: "GET" });
  }

  async retryReminder(reminderId: string): Promise<VisitReminderPublic> {
    return this.request<VisitReminderPublic>(`/reminders/${reminderId}/retry`, { method: "POST" });
  }

  async createBooking(payload: { lead_id: string; project_id: string; start_time: string }): Promise<SiteVisitPublic> {
    return this.request<SiteVisitPublic>("/bookings", { method: "POST", body: JSON.stringify(payload) });
  }

  async cancelBooking(bookingId: string): Promise<SiteVisitPublic> {
    return this.request<SiteVisitPublic>(`/bookings/${bookingId}/cancel`, { method: "POST" });
  }

  async rescheduleBooking(bookingId: string, startTime: string): Promise<SiteVisitPublic> {
    return this.request<SiteVisitPublic>(`/bookings/${bookingId}/reschedule`, {
      method: "POST",
      body: JSON.stringify({ start_time: startTime }),
    });
  }

  async recordAttendance(bookingId: string, attendanceStatus: "COMPLETED" | "NO_SHOW"): Promise<SiteVisitPublic> {
    return this.request<SiteVisitPublic>(`/bookings/${bookingId}/attendance`, {
      method: "POST",
      body: JSON.stringify({ status: attendanceStatus }),
    });
  }

  async getConversationMessages(
    conversationId: string,
    params: { limit?: number; offset?: number } = {}
  ): Promise<MessageListResponse> {
    const query = new URLSearchParams();
    if (params.limit !== undefined) query.set("limit", String(params.limit));
    if (params.offset !== undefined) query.set("offset", String(params.offset));
    return this.request<MessageListResponse>(
      `/conversations/${conversationId}/messages?${query.toString()}`,
      { method: "GET" }
    );
  }

  async sendStaffMessage(conversationId: string, content: string): Promise<MessagePublic> {
    return this.request<MessagePublic>(`/conversations/${conversationId}/messages`, {
      method: "POST",
      body: JSON.stringify({ content }),
    });
  }

  async requestHandoff(
    conversationId: string,
    payload: { reason?: HandoffReason; summary?: string } = {}
  ): Promise<HandoffPublic> {
    return this.request<HandoffPublic>(`/conversations/${conversationId}/handoff`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
  }

  async transitionOwnership(conversationId: string, ownershipStatus: OwnershipStatus): Promise<ConversationListItem> {
    return this.request<ConversationListItem>(`/conversations/${conversationId}/ownership`, {
      method: "POST",
      body: JSON.stringify({ ownership_status: ownershipStatus }),
    });
  }

  // --- Human Handoff & Sales Workspace (Feature 06) ---

  async listHandoffs(params: {
    status?: HandoffStatus;
    mine?: boolean;
    limit?: number;
    offset?: number;
  } = {}): Promise<HandoffListResponse> {
    const query = new URLSearchParams();
    if (params.status) query.set("status", params.status);
    if (params.mine !== undefined) query.set("mine", String(params.mine));
    if (params.limit !== undefined) query.set("limit", String(params.limit));
    if (params.offset !== undefined) query.set("offset", String(params.offset));
    return this.request<HandoffListResponse>(`/handoffs?${query.toString()}`, { method: "GET" });
  }

  async getHandoff(handoffId: string): Promise<HandoffDetail> {
    return this.request<HandoffDetail>(`/handoffs/${handoffId}`, { method: "GET" });
  }

  async acceptHandoff(handoffId: string): Promise<HandoffDetail> {
    return this.request<HandoffDetail>(`/handoffs/${handoffId}/accept`, { method: "POST" });
  }

  async rejectHandoff(handoffId: string, reason?: string): Promise<HandoffDetail> {
    return this.request<HandoffDetail>(`/handoffs/${handoffId}/reject`, {
      method: "POST",
      body: JSON.stringify({ reason }),
    });
  }

  async reassignHandoff(handoffId: string, executiveId: string): Promise<HandoffDetail> {
    return this.request<HandoffDetail>(`/handoffs/${handoffId}/reassign`, {
      method: "POST",
      body: JSON.stringify({ executive_id: executiveId }),
    });
  }

  async resolveHandoff(handoffId: string): Promise<HandoffDetail> {
    return this.request<HandoffDetail>(`/handoffs/${handoffId}/resolve`, { method: "POST" });
  }

  // --- Analytics & Business Intelligence (Feature 08) ---

  async getOverviewAnalytics(filters: AnalyticsFilterParams = {}): Promise<OverviewAnalytics> {
    return this.request<OverviewAnalytics>(`/analytics/overview?${buildAnalyticsQuery(filters)}`, { method: "GET" });
  }

  async getLeadAnalytics(filters: AnalyticsFilterParams = {}): Promise<LeadAnalytics> {
    return this.request<LeadAnalytics>(`/analytics/leads?${buildAnalyticsQuery(filters)}`, { method: "GET" });
  }

  async getSourceAnalytics(filters: AnalyticsFilterParams = {}): Promise<SourceAnalytics> {
    return this.request<SourceAnalytics>(`/analytics/sources?${buildAnalyticsQuery(filters)}`, { method: "GET" });
  }

  async getResponseTimeAnalytics(filters: AnalyticsFilterParams = {}): Promise<ResponseTimeAnalytics> {
    return this.request<ResponseTimeAnalytics>(`/analytics/response-times?${buildAnalyticsQuery(filters)}`, { method: "GET" });
  }

  async getQualificationAnalytics(filters: AnalyticsFilterParams = {}): Promise<QualificationAnalytics> {
    return this.request<QualificationAnalytics>(`/analytics/qualification?${buildAnalyticsQuery(filters)}`, { method: "GET" });
  }

  async getFunnelAnalytics(filters: AnalyticsFilterParams = {}): Promise<FunnelAnalytics> {
    return this.request<FunnelAnalytics>(`/analytics/funnel?${buildAnalyticsQuery(filters)}`, { method: "GET" });
  }

  async getSiteVisitAnalytics(
    filters: AnalyticsFilterParams = {},
    dateBasis: VisitDateBasis = "BOOKING"
  ): Promise<SiteVisitAnalytics> {
    const query = buildAnalyticsQuery(filters);
    return this.request<SiteVisitAnalytics>(`/analytics/site-visits?${query}&date_basis=${dateBasis}`, { method: "GET" });
  }

  async getExecutiveAnalytics(filters: AnalyticsFilterParams = {}): Promise<ExecutiveAnalytics> {
    return this.request<ExecutiveAnalytics>(`/analytics/executives?${buildAnalyticsQuery(filters)}`, { method: "GET" });
  }

  async getReminderAnalytics(
    filters: AnalyticsFilterParams = {},
    dateBasis: ReminderDateBasis = "CREATED"
  ): Promise<ReminderAnalytics> {
    const query = buildAnalyticsQuery(filters);
    return this.request<ReminderAnalytics>(`/analytics/reminders?${query}&date_basis=${dateBasis}`, { method: "GET" });
  }
}

export const apiClient = new ApiClient(API_BASE_URL);
