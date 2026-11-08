"use client";

import React, { useState } from "react";
import Link from "next/link";
import { Building2, Menu, X } from "lucide-react";

const NAV_LINKS = [
  { label: "Home", href: "/" },
  { label: "Explore Projects", href: "/projects" },
  { label: "About Us", href: "/#about" },
  { label: "Contact", href: "/#contact" },
];

export function PublicNavbar() {
  const [open, setOpen] = useState(false);

  return (
    <header className="sticky top-0 z-40 bg-[#F7F6F2]/95 backdrop-blur-sm border-b border-[#E5E5DE]">
      <nav
        aria-label="Primary"
        className="max-w-7xl mx-auto h-16 px-4 md:px-8 flex items-center justify-between"
      >
        <Link href="/" className="flex items-center gap-2.5 shrink-0">
          <div className="w-9 h-9 rounded-lg bg-[#173B35] flex items-center justify-center shadow-sm">
            <Building2 className="w-5 h-5 text-white" />
          </div>
          <span className="font-heading font-bold text-lg text-[#202B28] tracking-tight">
            EstateFlow <span className="text-[#C47A55]">AI</span>
          </span>
        </Link>

        <div className="hidden md:flex items-center gap-8">
          {NAV_LINKS.map((link) => (
            <Link
              key={link.label}
              href={link.href}
              className="text-sm font-medium text-[#202B28] hover:text-[#173B35] transition-colors"
            >
              {link.label}
            </Link>
          ))}
        </div>

        <div className="hidden md:flex items-center gap-3">
          <Link
            href="/login"
            className="text-xs font-medium text-[#737C76] hover:text-[#202B28] transition-colors"
          >
            Staff Login
          </Link>
          <Link
            href="/customer/login"
            className="h-10 px-4 rounded-lg border border-[#E5E5DE] text-sm font-semibold text-[#202B28] flex items-center hover:bg-[#F0F1EC] transition-colors"
          >
            Sign In
          </Link>
          <Link
            href="/customer/signup"
            className="h-10 px-4 rounded-lg bg-[#173B35] hover:bg-[#1f4b43] text-white text-sm font-semibold flex items-center transition-colors"
          >
            Create Account
          </Link>
        </div>

        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          aria-label={open ? "Close menu" : "Open menu"}
          aria-expanded={open}
          className="md:hidden w-10 h-10 rounded-lg border border-[#E5E5DE] flex items-center justify-center text-[#202B28]"
        >
          {open ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
        </button>
      </nav>

      {open && (
        <div className="md:hidden border-t border-[#E5E5DE] bg-[#F7F6F2] px-4 py-4 space-y-3">
          {NAV_LINKS.map((link) => (
            <Link
              key={link.label}
              href={link.href}
              onClick={() => setOpen(false)}
              className="block text-sm font-medium text-[#202B28] py-2"
            >
              {link.label}
            </Link>
          ))}
          <div className="flex flex-col gap-2 pt-2">
            <Link
              href="/customer/login"
              onClick={() => setOpen(false)}
              className="h-10 px-4 rounded-lg border border-[#E5E5DE] text-sm font-semibold text-[#202B28] flex items-center justify-center"
            >
              Sign In
            </Link>
            <Link
              href="/customer/signup"
              onClick={() => setOpen(false)}
              className="h-10 px-4 rounded-lg bg-[#173B35] text-white text-sm font-semibold flex items-center justify-center"
            >
              Create Account
            </Link>
            <Link
              href="/login"
              onClick={() => setOpen(false)}
              className="text-xs text-center text-[#737C76] py-1"
            >
              Staff Login
            </Link>
          </div>
        </div>
      )}
    </header>
  );
}
