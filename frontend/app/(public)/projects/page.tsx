"use client";

import React, { useEffect, useState } from "react";
import { Search, MapPin, AlertCircle, Loader2, Building2 } from "lucide-react";
import { apiClient, ApiError, PublicProjectCard as PublicProjectCardType } from "@/lib/api-client";
import { ProjectCard } from "@/components/public/project-card";

const PAGE_SIZE = 9;

export default function PublicProjectsPage() {
  const [search, setSearch] = useState("");
  const [location, setLocation] = useState("");
  const [appliedSearch, setAppliedSearch] = useState("");
  const [appliedLocation, setAppliedLocation] = useState("");
  const [offset, setOffset] = useState(0);

  const [items, setItems] = useState<PublicProjectCardType[] | null>(null);
  const [total, setTotal] = useState(0);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- intentional reset on filter/page change
    setItems(null);
    setError(null);
    apiClient
      .getPublicProjects({
        search: appliedSearch || undefined,
        location: appliedLocation || undefined,
        limit: PAGE_SIZE,
        offset,
      })
      .then((data) => {
        if (cancelled) return;
        setItems(data.items);
        setTotal(data.total);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err instanceof ApiError ? err.message : "Failed to load projects.");
      });
    return () => {
      cancelled = true;
    };
  }, [appliedSearch, appliedLocation, offset]);

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    setOffset(0);
    setAppliedSearch(search.trim());
    setAppliedLocation(location.trim());
  };

  const hasNextPage = offset + PAGE_SIZE < total;
  const hasPrevPage = offset > 0;

  return (
    <div className="max-w-7xl mx-auto px-4 md:px-8 py-12">
      <div className="text-center max-w-2xl mx-auto">
        <h1 className="font-heading font-bold text-3xl md:text-4xl text-[#202B28] tracking-tight">
          Explore Our Projects
        </h1>
        <p className="text-sm md:text-base text-[#737C76] mt-3">
          Browse published residential projects by name or location.
        </p>
      </div>

      <form
        onSubmit={handleSearch}
        className="mt-8 bg-white rounded-xl border border-[#E5E5DE] shadow-xs p-4 flex flex-col sm:flex-row gap-3"
      >
        <div className="flex-1 relative">
          <Search className="w-4 h-4 text-[#9FAAA4] absolute left-3 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search by project name"
            aria-label="Search by project name"
            className="w-full h-11 pl-10 pr-3 rounded-lg border border-[#E5E5DE] text-sm focus:outline-none focus:ring-2 focus:ring-[#315C50]"
          />
        </div>
        <div className="flex-1 relative">
          <MapPin className="w-4 h-4 text-[#9FAAA4] absolute left-3 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            value={location}
            onChange={(e) => setLocation(e.target.value)}
            placeholder="Filter by location"
            aria-label="Filter by location"
            className="w-full h-11 pl-10 pr-3 rounded-lg border border-[#E5E5DE] text-sm focus:outline-none focus:ring-2 focus:ring-[#315C50]"
          />
        </div>
        <button
          type="submit"
          className="h-11 px-6 rounded-lg bg-[#173B35] hover:bg-[#1f4b43] text-white text-sm font-semibold transition-colors"
        >
          Search
        </button>
      </form>

      <div className="mt-10">
        {error && (
          <div className="flex items-center gap-2 text-sm text-[#C34D4D] bg-[#FDF2F2] border border-[#F8D2D2] rounded-lg px-4 py-3">
            <AlertCircle className="w-4 h-4 shrink-0" />
            {error}
          </div>
        )}

        {!error && items === null && (
          <div className="flex items-center justify-center py-20 text-[#737C76] text-sm gap-2">
            <Loader2 className="w-4 h-4 animate-spin" />
            Loading projects...
          </div>
        )}

        {!error && items !== null && items.length === 0 && (
          <div className="text-center py-20 bg-white rounded-xl border border-[#E5E5DE]">
            <Building2 className="w-8 h-8 text-[#C5C5BB] mx-auto" aria-hidden="true" />
            <p className="text-sm text-[#737C76] mt-3">
              No published projects match your search. Try a different name or location.
            </p>
          </div>
        )}

        {!error && items !== null && items.length > 0 && (
          <>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
              {items.map((project) => (
                <ProjectCard key={project.id} project={project} />
              ))}
            </div>

            <div className="flex items-center justify-between mt-8">
              <button
                type="button"
                disabled={!hasPrevPage}
                onClick={() => setOffset((o) => Math.max(0, o - PAGE_SIZE))}
                className="h-10 px-4 rounded-lg border border-[#E5E5DE] text-sm font-semibold text-[#202B28] disabled:opacity-40 disabled:cursor-not-allowed hover:bg-[#F0F1EC] transition-colors"
              >
                Previous
              </button>
              <span className="text-xs text-[#737C76]">
                Showing {Math.min(offset + 1, total)}-{Math.min(offset + PAGE_SIZE, total)} of {total}
              </span>
              <button
                type="button"
                disabled={!hasNextPage}
                onClick={() => setOffset((o) => o + PAGE_SIZE)}
                className="h-10 px-4 rounded-lg border border-[#E5E5DE] text-sm font-semibold text-[#202B28] disabled:opacity-40 disabled:cursor-not-allowed hover:bg-[#F0F1EC] transition-colors"
              >
                Next
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
