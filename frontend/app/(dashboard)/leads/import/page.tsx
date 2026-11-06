"use client";

import React, { useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowLeft, CheckCircle2, FileSpreadsheet, Loader2, XCircle } from "lucide-react";
import { useAuth } from "@/lib/auth-context";
import { apiClient, ApiError, CsvImportResponse } from "@/lib/api-client";

export default function LeadImportPage() {
  const { user } = useAuth();
  const router = useRouter();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [file, setFile] = useState<File | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<CsvImportResponse | null>(null);

  const canImport = user && (user.role === "ADMIN" || user.role === "MANAGER");

  const handleImport = async () => {
    if (!file) return;
    setSubmitting(true);
    setError(null);
    setResult(null);
    try {
      const response = await apiClient.importLeadsCsv(file);
      setResult(response);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "CSV import failed.");
    } finally {
      setSubmitting(false);
    }
  };

  if (!user) return null;

  if (!canImport) {
    return (
      <p className="text-sm text-[#737C76]">
        CSV import is restricted to managers and administrators.
      </p>
    );
  }

  return (
    <div className="space-y-6 max-w-3xl">
      <button
        onClick={() => router.push("/leads")}
        className="flex items-center gap-1.5 text-sm text-[#737C76] hover:text-[#202B28]"
      >
        <ArrowLeft className="w-4 h-4" />
        Back to leads
      </button>

      <div>
        <h1 className="text-2xl font-bold font-heading text-[#202B28] tracking-tight">Import Leads from CSV</h1>
        <p className="text-sm text-[#737C76] mt-1">
          Required columns: <code>full_name</code>, <code>phone</code>. Optional:{" "}
          <code>email</code>, <code>preferred_language</code>, <code>campaign_name</code>,{" "}
          <code>external_lead_id</code>.
        </p>
      </div>

      <div className="bg-white rounded-xl border border-[#E5E5DE] shadow-xs p-6 space-y-4">
        <div
          onClick={() => fileInputRef.current?.click()}
          className="border-2 border-dashed border-[#E5E5DE] rounded-lg p-8 text-center cursor-pointer hover:border-[#315C50] transition-colors"
        >
          <FileSpreadsheet className="w-8 h-8 text-[#9EA69F] mx-auto mb-3" />
          <p className="text-sm text-[#202B28] font-medium">{file ? file.name : "Click to choose a .csv file"}</p>
          <p className="text-xs text-[#737C76] mt-1">Max file size and row count are enforced server-side.</p>
          <input
            ref={fileInputRef}
            type="file"
            accept=".csv"
            className="hidden"
            onChange={(e) => {
              setResult(null);
              setError(null);
              setFile(e.target.files?.[0] || null);
            }}
          />
        </div>

        {error && <p className="text-sm text-[#C34D4D]">{error}</p>}

        <button
          onClick={handleImport}
          disabled={!file || submitting}
          className="h-10 px-4 rounded-lg bg-[#173B35] hover:bg-[#1f4b43] disabled:opacity-60 text-white text-sm font-semibold flex items-center gap-2"
        >
          {submitting && <Loader2 className="w-4 h-4 animate-spin" />}
          Import
        </button>
      </div>

      {result && (
        <div className="bg-white rounded-xl border border-[#E5E5DE] shadow-xs">
          <div className="px-6 py-4 border-b border-[#E5E5DE] grid grid-cols-4 gap-4 text-center">
            <div>
              <p className="text-lg font-bold text-[#202B28]">{result.total_rows}</p>
              <p className="text-xs text-[#737C76]">Total rows</p>
            </div>
            <div>
              <p className="text-lg font-bold text-[#27845B]">{result.created}</p>
              <p className="text-xs text-[#737C76]">Created</p>
            </div>
            <div>
              <p className="text-lg font-bold text-[#4779A8]">{result.matched}</p>
              <p className="text-xs text-[#737C76]">Matched existing</p>
            </div>
            <div>
              <p className="text-lg font-bold text-[#C34D4D]">{result.failed}</p>
              <p className="text-xs text-[#737C76]">Failed</p>
            </div>
          </div>
          <ul className="divide-y divide-[#F0F1EC] max-h-96 overflow-y-auto">
            {result.results.map((row) => (
              <li key={row.row_number} className="px-6 py-3 flex items-center gap-3 text-sm">
                {row.status === "FAILED" ? (
                  <XCircle className="w-4 h-4 text-[#C34D4D] shrink-0" />
                ) : (
                  <CheckCircle2 className="w-4 h-4 text-[#27845B] shrink-0" />
                )}
                <span className="text-[#737C76]">Row {row.row_number}:</span>
                <span className="text-[#202B28] font-medium">{row.status.replace(/_/g, " ")}</span>
                {row.message && <span className="text-[#C34D4D] text-xs">{row.message}</span>}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
