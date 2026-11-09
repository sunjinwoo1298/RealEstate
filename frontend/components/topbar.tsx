"use client";

import React from "react";
import { useRouter, usePathname } from "next/navigation";
import { useAuth } from "@/lib/auth-context";
import { LogOut } from "lucide-react";

const ROLE_LABELS: Record<string, string> = {
  ADMIN: "Admin",
  MANAGER: "Manager",
  SALES_EXECUTIVE: "Sales Executive",
};

const SECTION_TITLES: Array<[string, string]> = [
  ["/leads/duplicates", "Duplicate review"],
  ["/leads/import", "Import leads"],
  ["/leads", "Leads"],
  ["/conversations", "Conversations"],
  ["/handoff", "Handoff queue"],
  ["/visits", "Site visits"],
  ["/admin/availability", "Availability"],
  ["/admin/staff", "Staff accounts"],
  ["/knowledge", "Knowledge base"],
  ["/analytics", "Analytics"],
  ["/dashboard", "Dashboard"],
];

function sectionTitle(pathname: string | null): string {
  const match = SECTION_TITLES.find(([prefix]) => pathname?.startsWith(prefix));
  return match ? match[1] : "Dashboard";
}

export function Topbar() {
  const { user, logout } = useAuth();
  const router = useRouter();

  const pathname = usePathname();

  const handleLogout = async () => {
    await logout();
    router.replace("/login");
  };

  const initials = user?.full_name
    ? user.full_name
        .split(" ")
        .map((part) => part[0])
        .slice(0, 2)
        .join("")
        .toUpperCase()
    : "EF";

  return (
    <header className="h-16 bg-white border-b border-[#E5E5DE] px-6 flex items-center justify-between sticky top-0 z-20 shadow-xs">
      {/* Breadcrumb / Section */}
      <div className="flex items-center gap-2 text-sm text-[#737C76]">
        <span className="font-medium text-[#202B28]">EstateFlow</span>
        <span>/</span>
        <span className="text-[#173B35] font-semibold">{sectionTitle(pathname)}</span>
      </div>

      {/* Right Actions */}
      <div className="flex items-center gap-4">
        {/* User Profile */}
        <div className="flex items-center gap-3 pl-2 border-l border-[#E5E5DE]">
          <div className="w-8 h-8 rounded-full bg-[#173B35] text-white flex items-center justify-center font-semibold text-xs shadow-xs">
            {initials}
          </div>
          <div className="hidden md:flex flex-col text-left">
            <span className="text-xs font-semibold text-[#202B28]">
              {user?.full_name ?? "Unknown"}
            </span>
            <span className="text-[11px] text-[#737C76]">
              {user ? ROLE_LABELS[user.role] ?? user.role : ""}
            </span>
          </div>
          <button
            onClick={handleLogout}
            title="Log out"
            aria-label="Log out"
            className="w-9 h-9 rounded-lg border border-[#E5E5DE] hover:bg-[#F0F1EC] text-[#737C76] hover:text-[#C34D4D] flex items-center justify-center transition-colors"
          >
            <LogOut className="w-4 h-4" />
          </button>
        </div>
      </div>
    </header>
  );
}
