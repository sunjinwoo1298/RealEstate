"use client";

import React from "react";
import { useRouter } from "next/navigation";
import { Sidebar } from "@/components/sidebar";
import { Topbar } from "@/components/topbar";
import { useAuth } from "@/lib/auth-context";

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const { user, isLoading } = useAuth();
  const router = useRouter();

  React.useEffect(() => {
    if (!isLoading && !user) {
      router.replace("/login");
    }
  }, [isLoading, user, router]);

  if (isLoading) {
    return (
      <div className="h-screen w-screen flex items-center justify-center bg-[#F7F6F2] text-[#737C76] text-sm">
        Loading EstateFlow AI...
      </div>
    );
  }

  if (!user) {
    // Redirect is in flight; render nothing to avoid a protected-content flash.
    // Backend authorization remains authoritative regardless of this UX guard.
    return null;
  }

  return (
    <div className="flex flex-row overflow-hidden h-screen">
      <Sidebar />
      <div className="flex-1 flex flex-col min-w-0 h-screen overflow-y-auto">
        <Topbar />
        <main className="flex-1 p-6 md:p-8">{children}</main>
      </div>
    </div>
  );
}
