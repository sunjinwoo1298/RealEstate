"use client";

import React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { LogOut, Menu, X } from "lucide-react";
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
  const [open, setOpen] = React.useState(false);

  if (!customer) return null;

  const isActive = (href: string) =>
    pathname === href ||
    ((href === "/customer/chat" || href === "/customer/visits") && !!pathname?.startsWith(href));

  return (
    <>
      {/* Desktop / tablet: one row */}
      <nav className="hidden md:flex items-center gap-1" aria-label="Account">
        {NAV_ITEMS.map((item) => (
          <Link
            key={item.href}
            href={item.href}
            className={`px-3 py-2 rounded-lg text-sm font-semibold transition-colors ${
              isActive(item.href) ? "bg-[#173B35] text-white" : "text-[#202B28] hover:bg-[#F0F1EC]"
            }`}
          >
            {item.label}
          </Link>
        ))}
        <button
          onClick={() => logout()}
          className="flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm font-semibold text-[#737C76] hover:bg-[#F0F1EC] transition-colors"
        >
          <LogOut className="w-3.5 h-3.5" />
          Sign out
        </button>
      </nav>

      {/* Phone: menu button + dropdown panel */}
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-label={open ? "Close menu" : "Open menu"}
        aria-expanded={open}
        className="md:hidden w-10 h-10 rounded-lg border border-[#E5E5DE] bg-white flex items-center justify-center text-[#202B28]"
      >
        {open ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
      </button>
      {open && (
        <nav
          aria-label="Account"
          className="md:hidden absolute left-0 right-0 top-16 z-30 bg-white border-b border-[#E5E5DE] shadow-sm p-2 flex flex-col"
        >
          {NAV_ITEMS.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              onClick={() => setOpen(false)}
              className={`px-4 py-3 rounded-lg text-base font-semibold ${
                isActive(item.href) ? "bg-[#173B35] text-white" : "text-[#202B28] active:bg-[#F0F1EC]"
              }`}
            >
              {item.label}
            </Link>
          ))}
          <button
            onClick={() => {
              setOpen(false);
              logout();
            }}
            className="flex items-center gap-2 px-4 py-3 rounded-lg text-base font-semibold text-[#737C76] text-left"
          >
            <LogOut className="w-4 h-4" />
            Sign out
          </button>
        </nav>
      )}
    </>
  );
}
