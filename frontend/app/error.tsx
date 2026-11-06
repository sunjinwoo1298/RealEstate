"use client";

import React, { useEffect } from "react";
import { AlertCircle, RefreshCw } from "lucide-react";

export default function ErrorBoundary({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("Unhandled client error:", error);
  }, [error]);

  return (
    <div className="w-full min-h-[400px] flex items-center justify-center p-6">
      <div className="max-w-md w-full bg-white p-6 rounded-xl border border-[#E5E5DE] shadow-xs text-center space-y-4">
        <div className="w-12 h-12 rounded-full bg-[#FDF2F2] border border-[#F8D2D2] text-[#C34D4D] flex items-center justify-center mx-auto">
          <AlertCircle className="w-6 h-6" />
        </div>
        <div>
          <h2 className="text-lg font-bold font-heading text-[#202B28]">
            Something went wrong
          </h2>
          <p className="text-xs text-[#737C76] mt-1">
            {error.message || "An unexpected error occurred while loading this view."}
          </p>
        </div>
        <button
          onClick={() => reset()}
          className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-[#173B35] hover:bg-[#315C50] text-white text-xs font-semibold shadow-xs transition-colors"
        >
          <RefreshCw className="w-3.5 h-3.5" />
          Try Again
        </button>
      </div>
    </div>
  );
}

