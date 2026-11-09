"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import {
  MapPin,
  Layers,
  CheckCircle2,
  FileText,
  MessageSquare,
  CalendarCheck,
  ArrowRight,
  ArrowLeft,
  AlertCircle,
  Loader2,
  Building2,
  Image as ImageIcon,
} from "lucide-react";
import { apiClient, ApiError, PublicProjectDetail } from "@/lib/api-client";

export default function PublicProjectDetailPage() {
  const params = useParams<{ id: string }>();

  const [project, setProject] = useState<PublicProjectDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- intentional reset on id change
    setLoading(true);
    setError(null);
    setNotFound(false);
    apiClient
      .getPublicProject(params.id)
      .then((data) => {
        if (!cancelled) setProject(data);
      })
      .catch((err) => {
        if (cancelled) return;
        if (err instanceof ApiError && err.status === 404) {
          setNotFound(true);
        } else {
          setError(err instanceof ApiError ? err.message : "Failed to load this project.");
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [params.id]);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-24 text-[#737C76] text-sm gap-2">
        <Loader2 className="w-4 h-4 animate-spin" />
        Loading project...
      </div>
    );
  }

  if (notFound) {
    return (
      <div className="max-w-xl mx-auto px-4 py-24 text-center">
        <Building2 className="w-10 h-10 text-[#C5C5BB] mx-auto" aria-hidden="true" />
        <h1 className="font-heading font-bold text-xl text-[#202B28] mt-4">Project Unavailable</h1>
        <p className="text-sm text-[#737C76] mt-2">
          This project is not currently published, or the link is incorrect.
        </p>
        <Link
          href="/projects"
          className="inline-flex items-center gap-2 mt-6 h-10 px-4 rounded-lg bg-[#173B35] hover:bg-[#1f4b43] text-white text-sm font-semibold transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
          Explore other projects
        </Link>
      </div>
    );
  }

  if (error || !project) {
    return (
      <div className="max-w-xl mx-auto px-4 py-24 text-center">
        <AlertCircle className="w-8 h-8 text-[#C34D4D] mx-auto" />
        <p className="text-sm text-[#C34D4D] mt-3">{error ?? "Something went wrong."}</p>
      </div>
    );
  }

  const heroImage = project.images[0] ?? null;

  return (
    <div>
      <div className="h-72 md:h-96 bg-[#F0F1EC] relative">
        {heroImage ? (
          // eslint-disable-next-line @next/next/no-img-element -- external, admin-supplied URLs
          <img src={heroImage} alt={`Exterior view of ${project.name}`} className="w-full h-full object-cover" />
        ) : (
          <div className="w-full h-full flex items-center justify-center text-[#9FAAA4]">
            <ImageIcon className="w-14 h-14" aria-hidden="true" />
          </div>
        )}
        <div className="absolute inset-0 bg-gradient-to-t from-black/50 via-black/0 to-transparent" />
        <div className="absolute bottom-0 left-0 right-0 max-w-7xl mx-auto px-4 md:px-8 pb-6">
          <h1 className="font-heading font-bold text-3xl md:text-4xl text-white tracking-tight">
            {project.name}
          </h1>
          {project.location && (
            <p className="flex items-center gap-1.5 text-sm text-white/90 mt-1.5">
              <MapPin className="w-4 h-4" />
              {project.location}
            </p>
          )}
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-4 md:px-8 py-10 grid grid-cols-1 lg:grid-cols-3 gap-8">
        <div className="lg:col-span-2 space-y-8">
          {project.description && (
            <section>
              <h2 className="font-heading font-bold text-xl text-[#202B28]">Overview</h2>
              <p className="text-sm text-[#4F574F] mt-3 leading-relaxed whitespace-pre-line">
                {project.description}
              </p>
            </section>
          )}

          {project.configurations.length > 0 && (
            <section>
              <h2 className="font-heading font-bold text-xl text-[#202B28] flex items-center gap-2">
                <Layers className="w-5 h-5 text-[#173B35]" />
                Available Configurations
              </h2>
              <div className="flex flex-wrap gap-2 mt-3">
                {project.configurations.map((config) => (
                  <span
                    key={config}
                    className="text-sm font-medium px-3 py-1.5 rounded-lg bg-[#F0F1EC] text-[#202B28] border border-[#E5E5DE]"
                  >
                    {config}
                  </span>
                ))}
              </div>
            </section>
          )}

          {project.amenities.length > 0 && (
            <section>
              <h2 className="font-heading font-bold text-xl text-[#202B28]">Amenities</h2>
              <ul className="grid grid-cols-1 sm:grid-cols-2 gap-2.5 mt-3">
                {project.amenities.map((amenity) => (
                  <li key={amenity} className="flex items-center gap-2 text-sm text-[#202B28]">
                    <CheckCircle2 className="w-4 h-4 text-[#27845B] shrink-0" />
                    {amenity}
                  </li>
                ))}
              </ul>
            </section>
          )}

          {project.images.length > 1 && (
            <section>
              <h2 className="font-heading font-bold text-xl text-[#202B28]">Gallery</h2>
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 mt-3">
                {project.images.slice(1).map((src, idx) => (
                  // eslint-disable-next-line @next/next/no-img-element -- external, admin-supplied URLs
                  <img
                    key={src}
                    src={src}
                    alt={`${project.name} image ${idx + 2}`}
                    className="w-full h-32 object-cover rounded-lg border border-[#E5E5DE]"
                  />
                ))}
              </div>
            </section>
          )}

          {project.floor_plan_url && (
            <section>
              <h2 className="font-heading font-bold text-xl text-[#202B28] flex items-center gap-2">
                <FileText className="w-5 h-5 text-[#173B35]" />
                Floor Plan
              </h2>
              <a
                href={project.floor_plan_url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-2 mt-3 text-sm font-semibold text-[#173B35] hover:text-[#C47A55] transition-colors underline"
              >
                View floor plan / brochure
              </a>
            </section>
          )}

          {project.rera_number && (
            <p className="text-xs text-[#737C76]">RERA Registration: {project.rera_number}</p>
          )}
        </div>

        {/* Customer actions */}
        <aside className="space-y-4">
          <div className="bg-white rounded-xl border border-[#E5E5DE] shadow-xs p-6">
            <span className="text-sm font-semibold text-[#202B28]">
              {project.starting_price_label ?? "Price available on request"}
            </span>

            <div className="mt-5 space-y-3">
              <Link
                href="/customer/chat/new"
                className="w-full h-11 rounded-lg bg-[#173B35] hover:bg-[#315C50] text-white text-sm font-semibold flex items-center justify-center gap-2 transition-colors"
              >
                <MessageSquare className="w-4 h-4" />
                Ask our assistant
              </Link>
              <Link
                href="/customer/visits/book"
                className="w-full h-11 rounded-lg bg-[#C47A55] hover:bg-[#B26B48] text-white text-sm font-semibold flex items-center justify-center gap-2 transition-colors"
              >
                <CalendarCheck className="w-4 h-4" />
                Book a site visit
              </Link>
              <Link
                href="/#contact"
                className="w-full h-11 rounded-lg border border-[#E5E5DE] hover:bg-[#F0F1EC] text-sm font-semibold text-[#202B28] flex items-center justify-center transition-colors"
              >
                Contact the Sales Team
              </Link>
            </div>
          </div>

          <Link
            href="/projects"
            className="flex items-center justify-center gap-2 w-full h-11 rounded-lg border border-[#E5E5DE] hover:bg-white text-sm font-semibold text-[#173B35] transition-colors"
          >
            <ArrowRight className="w-4 h-4" />
            Explore other projects
          </Link>
        </aside>
      </div>
    </div>
  );
}
