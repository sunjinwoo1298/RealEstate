// Shared display constants for the customer chat inbox and conversation
// pages, per spec section 9's required ownership-status labels.
export const OWNERSHIP_LABEL: Record<string, string> = {
  AI_ACTIVE: "AI assistant is helping you",
  PENDING_ASSIGNMENT: "Connecting you with a salesperson",
  HUMAN_ACTIVE: "Chatting with a sales representative",
  RESOLVED: "Resolved",
};

export const OWNERSHIP_BADGE_CLASS: Record<string, string> = {
  AI_ACTIVE: "bg-[#EAF3EC] text-[#1F6B4A]",
  PENDING_ASSIGNMENT: "bg-[#FDF6EC] text-[#B9772F]",
  HUMAN_ACTIVE: "bg-[#E9F5EF] text-[#27845B]",
  RESOLVED: "bg-[#F0F1EC] text-[#737C76]",
};
