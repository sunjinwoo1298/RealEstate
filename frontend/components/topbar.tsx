"use client";

import React, { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { apiClient, ApiError, HealthResponse } from "@/lib/api-client";
import { useAuth } from "@/lib/auth-context";
import { Bell, RefreshCw, CheckCircle2, AlertCircle, XCircle, LogOut } from "lucide-react";

const ROLE_LABELS: Record<string, string> = {
  ADMIN: "Admin",
  MANAGER: "Manager",
  SALES_EXECUTIVE: "Sales Executive",
};

export function Topbar() {
  const { user, logout } = useAuth();
  const router = useRouter();

  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const fetchHealth = async () => {
    setLoading(true);
    try {
      const data = await apiClient.getHealth();
      setHealth(data);
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Backend offline");
      setHealth(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- intentional initial fetch + poll
    fetchHealth();
    const interval = setInterval(fetchHealth, 30000); // 30s poll
    return () => clearInterval(interval);
  }, []);

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
        <span className="text-[#173B35] font-semibold">Overview Dashboard</span>
      </div>

      {/* Right Actions */}
      <div className="flex items-center gap-4">
        {/* Backend Connectivity Status Badge */}
        <div
          onClick={fetchHealth}
          className="flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-medium cursor-pointer border transition-colors hover:opacity-90 select-none"
          title="Click to refresh backend connectivity"
        >
          {loading ? (
            <span className="flex items-center gap-1.5 text-[#737C76] bg-[#F0F1EC] px-2 py-0.5 rounded-full">
              <RefreshCw className="w-3 h-3 animate-spin text-[#173B35]" />
              Connecting...
            </span>
          ) : health?.database?.status === "healthy" ? (
            <span className="flex items-center gap-1.5 text-[#27845B] bg-[#E9F5EF] border border-[#C5E6D5] px-2.5 py-0.5 rounded-full">
              <CheckCircle2 className="w-3.5 h-3.5" />
              API & DB Online
            </span>
          ) : error ? (
            <span className="flex items-center gap-1.5 text-[#C34D4D] bg-[#FDF2F2] border border-[#F8D2D2] px-2.5 py-0.5 rounded-full">
              <XCircle className="w-3.5 h-3.5" />
              API Disconnected
            </span>
          ) : (
            <span className="flex items-center gap-1.5 text-[#B7791F] bg-[#FEF7EC] border border-[#FBE3BC] px-2.5 py-0.5 rounded-full">
              <AlertCircle className="w-3.5 h-3.5" />
              API Degraded
            </span>
          )}
        </div>

        {/* Notifications */}
        <button
          className="w-9 h-9 rounded-lg border border-[#E5E5DE] hover:bg-[#F0F1EC] text-[#737C76] flex items-center justify-center transition-colors"
          title="Notifications"
          aria-label="Notifications"
        >
          <Bell className="w-4 h-4" />
        </button>

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
