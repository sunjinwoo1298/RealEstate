"use client";

import React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { LogOut } from "lucide-react";
import { useCustomerAuth } from "@/lib/customer-auth-context";

const NAV_ITEMS = [
  { href: "/customer/dashboard", label: "Dashboard" },
  { href: "/customer/chat", label: "Chat" },
  { href: "/customer/visits", label: "Visits" },
  { href: "/customer/notifications", label: "Notifications" },
  { href: "/customer/profile", label: "My Profile" },
  { href: "/projects", label: "Projects" },
  { href: "/customer/settings", label: "Settings" },
];

// Rendered only once the customer is authenticated -- on /customer/login,
// /customer/signup, etc. `customer` is null and this renders nothing, so
// the header stays a bare logo on those public-facing auth pages.
export function CustomerNav() {
  const { customer, logout } = useCustomerAuth();
  const pathname = usePathname();

  if (!customer) return null;

  return (
    <nav className="flex items-center gap-1">
      {NAV_ITEMS.map((item) => {
        const active =
          pathname === item.href ||
          ((item.href === "/customer/chat" || item.href === "/customer/visits") && pathname?.startsWith(item.href));
        return (
          <Link
            key={item.href}
            href={item.href}
            className={`px-3 py-2 rounded-lg text-sm font-semibold transition-colors ${
              active ? "bg-[#173B35] text-white" : "text-[#202B28] hover:bg-[#F0F1EC]"
            }`}
          >
            {item.label}
          </Link>
        );
      })}
      <button
        onClick={() => logout()}
        className="flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm font-semibold text-[#737C76] hover:bg-[#F0F1EC] transition-colors"
      >
        <LogOut className="w-3.5 h-3.5" />
        Sign out
      </button>
    </nav>
  );
}
