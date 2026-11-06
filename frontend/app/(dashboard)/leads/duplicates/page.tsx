"use client";

import React, { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowLeft, GitCompareArrows, Loader2 } from "lucide-react";
import { useAuth } from "@/lib/auth-context";
import { apiClient, ApiError, PotentialDuplicatePublic } from "@/lib/api-client";

export default function DuplicateReviewPage() {
  const { user } = useAuth();
  const router = useRouter();

  const [matches, setMatches] = useState<PotentialDuplicatePublic[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actingOn, setActingOn] = useState<string | null>(null);

  const canReview = user && (user.role === "ADMIN" || user.role === "MANAGER");

  const load = async () => {
    setLoading(true);
    try {
      const data = await apiClient.listPotentialDuplicates("PENDING_REVIEW");
      setMatches(data.items);
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load potential duplicates.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (canReview) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- intentional data fetch
      load();
    } else {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [canReview]);

  const handleReview = async (matchId: string, status: "CONFIRMED_DUPLICATE" | "REJECTED") => {
    setActingOn(matchId);
    try {
      await apiClient.reviewPotentialDuplicate(matchId, status);
      setMatches((prev) => prev.filter((m) => m.id !== matchId));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to record review decision.");
    } finally {
      setActingOn(null);
    }
  };

  if (!user) return null;

  if (!canReview) {
    return <p className="text-sm text-[#737C76]">Duplicate review is restricted to managers and administrators.</p>;
  }

  return (
    <div className="space-y-6">
      <button
        onClick={() => router.push("/leads")}
        className="flex items-center gap-1.5 text-sm text-[#737C76] hover:text-[#202B28]"
      >
        <ArrowLeft className="w-4 h-4" />
        Back to leads
      </button>

      <div>
        <h1 className="text-2xl font-bold font-heading text-[#202B28] tracking-tight">Potential Duplicate Review</h1>
        <p className="text-sm text-[#737C76] mt-1">
          These pairs share a similar name but no exact phone or email match, so they were never merged
          automatically. Confirm or reject each pairing based on manual review.
        </p>
      </div>

      {error && <p className="text-sm text-[#C34D4D]">{error}</p>}

      {loading ? (
        <div className="flex items-center justify-center py-16 text-sm text-[#737C76] gap-2">
          <Loader2 className="w-4 h-4 animate-spin" />
          Loading potential duplicates...
        </div>
      ) : matches.length === 0 ? (
        <div className="bg-white rounded-xl border border-[#E5E5DE] shadow-xs px-6 py-12 text-center">
          <GitCompareArrows className="w-8 h-8 text-[#C5C5BB] mx-auto mb-3" />
          <p className="text-sm text-[#737C76]">No potential duplicates pending review.</p>
        </div>
      ) : (
        <div className="space-y-4">
          {matches.map((match) => (
            <div key={match.id} className="bg-white rounded-xl border border-[#E5E5DE] shadow-xs p-6">
              <div className="flex items-center justify-between flex-wrap gap-4">
                <div className="grid grid-cols-2 gap-8 flex-1">
                  <div>
                    <p className="text-xs text-[#737C76] mb-1">New enquiry</p>
                    <p className="text-sm font-semibold text-[#202B28]">{match.new_lead?.full_name}</p>
                    <p className="text-xs text-[#737C76]">{match.new_lead?.normalized_phone || "No phone on file"}</p>
                  </div>
                  <div>
                    <p className="text-xs text-[#737C76] mb-1">Existing buyer</p>
                    <p className="text-sm font-semibold text-[#202B28]">{match.existing_lead?.full_name}</p>
                    <p className="text-xs text-[#737C76]">
                      {match.existing_lead?.normalized_phone || "No phone on file"}
                    </p>
                  </div>
                </div>
                <span className="text-xs font-semibold px-2 py-1 rounded-md bg-[#FDF3E7] text-[#B7791F] shrink-0">
                  {match.similarity_score ? `${Math.round(match.similarity_score * 100)}% name match` : match.match_reason}
                </span>
              </div>
              <div className="flex items-center gap-2 mt-4 pt-4 border-t border-[#F0F1EC]">
                <button
                  disabled={actingOn === match.id}
                  onClick={() => handleReview(match.id, "REJECTED")}
                  className="h-9 px-4 rounded-lg border border-[#E5E5DE] hover:bg-[#F0F1EC] text-sm font-semibold text-[#202B28] disabled:opacity-60"
                >
                  Not a duplicate
                </button>
                <button
                  disabled={actingOn === match.id}
                  onClick={() => handleReview(match.id, "CONFIRMED_DUPLICATE")}
                  className="h-9 px-4 rounded-lg bg-[#173B35] hover:bg-[#1f4b43] text-white text-sm font-semibold disabled:opacity-60"
                >
                  Confirm duplicate
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
