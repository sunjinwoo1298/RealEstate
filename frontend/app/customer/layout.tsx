import React from "react";
import Link from "next/link";
import { Building2 } from "lucide-react";
import { CustomerAuthProvider } from "@/lib/customer-auth-context";
import { CustomerNav } from "@/components/customer/customer-nav";

export default function CustomerLayout({ children }: { children: React.ReactNode }) {
  return (
    <CustomerAuthProvider>
      <div className="min-h-screen w-full bg-[#F7F6F2] flex flex-col">
        <header className="h-16 flex items-center justify-between px-4 md:px-8 border-b border-[#E5E5DE]">
          <Link href="/" className="flex items-center gap-2.5">
            <div className="w-9 h-9 rounded-lg bg-[#173B35] flex items-center justify-center shadow-sm">
              <Building2 className="w-5 h-5 text-white" />
            </div>
            <span className="font-heading font-bold text-lg text-[#202B28] tracking-tight">
              EstateFlow <span className="text-[#C47A55]">AI</span>
            </span>
          </Link>
          <CustomerNav />
        </header>
        <main className="flex-1 flex justify-center px-4 py-10">{children}</main>
      </div>
    </CustomerAuthProvider>
  );
}
