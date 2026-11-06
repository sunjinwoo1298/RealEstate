import React from "react";
import Link from "next/link";
import { FileQuestion, ArrowLeft } from "lucide-react";

export default function NotFound() {
  return (
    <div className="w-full min-h-[400px] flex items-center justify-center p-6">
      <div className="max-w-md w-full bg-white p-6 rounded-xl border border-[#E5E5DE] shadow-xs text-center space-y-4">
        <div className="w-12 h-12 rounded-full bg-[#F0F1EC] text-[#173B35] flex items-center justify-center mx-auto">
          <FileQuestion className="w-6 h-6" />
        </div>
        <div>
          <h2 className="text-xl font-bold font-heading text-[#202B28]">
            Page Not Found
          </h2>
          <p className="text-xs text-[#737C76] mt-1">
            The requested page does not exist or has been moved.
          </p>
        </div>
        <Link
          href="/"
          className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-[#173B35] hover:bg-[#315C50] text-white text-xs font-semibold shadow-xs transition-colors"
        >
          <ArrowLeft className="w-3.5 h-3.5" />
          Back to Dashboard
        </Link>
      </div>
    </div>
  );
}

