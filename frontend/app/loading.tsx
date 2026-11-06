import React from "react";

export default function Loading() {
  return (
    <div className="w-full h-full min-h-[400px] flex flex-col items-center justify-center space-y-4">
      <div className="w-10 h-10 border-3 border-[#E5E5DE] border-t-[#173B35] rounded-full animate-spin" />
      <div className="text-center">
        <p className="text-sm font-semibold text-[#202B28] font-heading">
          Loading EstateFlow...
        </p>
        <p className="text-xs text-[#737C76] mt-0.5">Fetching latest records</p>
      </div>
    </div>
  );
}

