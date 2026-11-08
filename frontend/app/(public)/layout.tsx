import React from "react";
import { PublicNavbar } from "@/components/public/navbar";
import { PublicFooter } from "@/components/public/footer";

export default function PublicLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen flex flex-col bg-[#F7F6F2]">
      <PublicNavbar />
      <main className="flex-1">{children}</main>
      <PublicFooter />
    </div>
  );
}
