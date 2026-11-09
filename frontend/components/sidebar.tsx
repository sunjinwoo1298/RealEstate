"use client";

import React, { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  Users,
  MessageSquare,
  CalendarDays,
  FileText,
  BarChart3,
  ChevronLeft,
  ChevronRight,
  Building2,
  ShieldCheck,
  UserCog,
  Headset,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useAuth } from "@/lib/auth-context";
import { UserRole } from "@/lib/api-client";

interface NavItem {
  label: string;
  href: string;
  icon: React.ElementType;
  roles?: UserRole[];
}

const navItems: NavItem[] = [
  { label: "Dashboard", href: "/dashboard", icon: LayoutDashboard },
  { label: "Leads", href: "/leads", icon: Users },
  { label: "Conversations", href: "/conversations", icon: MessageSquare },
  { label: "Handoff Queue", href: "/handoff", icon: Headset },
  { label: "Site Visits", href: "/visits", icon: CalendarDays },
  { label: "Availability", href: "/admin/availability", icon: CalendarDays, roles: ["ADMIN", "MANAGER"] },
  { label: "Knowledge Base", href: "/knowledge", icon: FileText, roles: ["ADMIN"] },
  { label: "Analytics", href: "/analytics", icon: BarChart3 },
  { label: "Staff Accounts", href: "/admin/staff", icon: UserCog, roles: ["ADMIN"] },
];

export function Sidebar() {
  const [collapsed, setCollapsed] = useState(false);
  const pathname = usePathname();
  const { user } = useAuth();

  const visibleNavItems = navItems.filter(
    (item) => !item.roles || (user && item.roles.includes(user.role))
  );

  return (
    <aside
      className={cn(
        "flex flex-col h-screen sticky top-0 transition-all duration-300 z-30 select-none",
        "bg-[#142F2B] text-white border-r border-[#173B35]",
        collapsed ? "w-[72px]" : "w-[256px]"
      )}
    >
      {/* Brand Header */}
      <div className="h-16 flex items-center justify-between px-4 border-b border-[#1b3d37]">
        <Link href="/dashboard" className="flex items-center gap-3 overflow-hidden">
          <div className="w-9 h-9 rounded-lg bg-[#C47A55] flex items-center justify-center shrink-0 shadow-sm">
            <Building2 className="w-5 h-5 text-white" />
          </div>
          {!collapsed && (
            <div className="flex flex-col min-w-0">
              <span className="font-heading font-bold text-base tracking-tight truncate text-white">
                EstateFlow <span className="text-[#C47A55]">AI</span>
              </span>
              <span className="text-[11px] text-[#A3B8B0] truncate tracking-wider uppercase font-medium">
                Developer Suite
              </span>
            </div>
          )}
        </Link>
        <button
          onClick={() => setCollapsed(!collapsed)}
          className="w-7 h-7 rounded-md bg-[#173B35] hover:bg-[#315C50] text-[#A3B8B0] hover:text-white flex items-center justify-center transition-colors"
          title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        >
          {collapsed ? (
            <ChevronRight className="w-4 h-4" />
          ) : (
            <ChevronLeft className="w-4 h-4" />
          )}
        </button>
      </div>

      {/* Navigation */}
      <nav className="flex-1 py-4 px-3 space-y-1 overflow-y-auto">
        {visibleNavItems.map((item) => {
          const Icon = item.icon;
          const isActive = pathname === item.href;
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all group",
                isActive
                  ? "bg-[#315C50] text-white shadow-sm"
                  : "text-[#D1DDD7] hover:bg-[#1a3833] hover:text-white"
              )}
              title={collapsed ? item.label : undefined}
            >
              <Icon
                className={cn(
                  "w-5 h-5 shrink-0 transition-colors",
                  isActive ? "text-[#C47A55]" : "text-[#9EBAAF] group-hover:text-white"
                )}
              />
              {!collapsed && (
                <span className="truncate flex-1">{item.label}</span>
              )}
            </Link>
          );
        })}
      </nav>

      {/* Footer Info */}
      <div className="p-3 border-t border-[#1b3d37]">
        <div
          className={cn(
            "rounded-lg bg-[#102522] p-2.5 flex items-center gap-2.5",
            collapsed && "justify-center"
          )}
        >
          <ShieldCheck className="w-4 h-4 text-[#27845B] shrink-0" />
          {!collapsed && (
            <div className="text-[11px] text-[#9EBAAF] leading-tight truncate">
              <p className="font-semibold text-white">Foundation Ready</p>
              <p className="truncate">Prisma Postgres</p>
            </div>
          )}
        </div>
      </div>
    </aside>
  );
}
