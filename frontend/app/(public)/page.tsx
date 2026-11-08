"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import {
  ArrowRight,
  Compass,
  MessageCircle,
  CalendarCheck,
  Search,
  AlertCircle,
  Loader2,
} from "lucide-react";
import { apiClient, ApiError, PublicProjectCard as PublicProjectCardType } from "@/lib/api-client";
import { ProjectCard } from "@/components/public/project-card";

const JOURNEY_STEPS = [
  {
    icon: Search,
    title: "Explore residential projects",
    description: "Browse published projects by location, configuration and amenities.",
  },
  {
    icon: Compass,
    title: "Discover project details",
    description: "Review configurations, amenities, images and location for each project.",
  },
  {
    icon: MessageCircle,
    title: "Get assistance with property-related questions",
    description: "Ask our AI assistant for help -- coming soon for registered customers.",
  },
  {
    icon: CalendarCheck,
    title: "Schedule a site visit",
    description: "Book a convenient time to visit in person -- coming soon for registered customers.",
  },
];

export default function PublicHomePage() {
  const [featured, setFeatured] = useState<PublicProjectCardType[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiClient
      .getFeaturedProjects(6)
      .then((data) => setFeatured(data.items))
      .catch((err) => setError(err instanceof ApiError ? err.message : "Failed to load featured projects."));
  }, []);

  return (
    <>
      {/* Hero */}
      <section className="relative overflow-hidden">
        <div className="max-w-7xl mx-auto px-4 md:px-8 py-20 md:py-28 text-center">
          <h1 className="font-heading font-bold text-4xl md:text-5xl text-[#202B28] tracking-tight max-w-3xl mx-auto">
            Find a home that fits your lifestyle.
          </h1>
          <p className="text-base md:text-lg text-[#4F574F] mt-5 max-w-2xl mx-auto leading-relaxed">
            Explore thoughtfully designed residential projects, discover the right home, and get
            the information you need to make a confident decision.
          </p>
          <div className="flex flex-col sm:flex-row items-center justify-center gap-3 mt-8">
            <Link
              href="/projects"
              className="h-12 px-6 rounded-lg bg-[#173B35] hover:bg-[#1f4b43] text-white text-sm font-semibold flex items-center gap-2 transition-colors shadow-sm"
            >
              Explore Projects
              <ArrowRight className="w-4 h-4" />
            </Link>
            <Link
              href="#featured"
              className="h-12 px-6 rounded-lg border border-[#C5C5BB] hover:bg-white text-[#202B28] text-sm font-semibold flex items-center transition-colors"
            >
              Discover Our Projects
            </Link>
          </div>
        </div>
      </section>

      {/* Featured Projects */}
      <section id="featured" className="max-w-7xl mx-auto px-4 md:px-8 py-14">
        <div className="flex items-center justify-between mb-8">
          <div>
            <h2 className="font-heading font-bold text-2xl md:text-3xl text-[#202B28] tracking-tight">
              Featured Projects
            </h2>
            <p className="text-sm text-[#737C76] mt-1">A selection of our published residential developments.</p>
          </div>
          <Link
            href="/projects"
            className="hidden sm:inline-flex items-center gap-1 text-sm font-semibold text-[#173B35] hover:text-[#C47A55] transition-colors shrink-0"
          >
            View all
            <ArrowRight className="w-3.5 h-3.5" />
          </Link>
        </div>

        {error && (
          <div className="flex items-center gap-2 text-sm text-[#C34D4D] bg-[#FDF2F2] border border-[#F8D2D2] rounded-lg px-4 py-3">
            <AlertCircle className="w-4 h-4 shrink-0" />
            {error}
          </div>
        )}

        {!error && featured === null && (
          <div className="flex items-center justify-center py-16 text-[#737C76] text-sm gap-2">
            <Loader2 className="w-4 h-4 animate-spin" />
            Loading featured projects...
          </div>
        )}

        {!error && featured !== null && featured.length === 0 && (
          <div className="text-center py-16 text-sm text-[#737C76] bg-white rounded-xl border border-[#E5E5DE]">
            No featured projects are published yet. Please check back soon, or{" "}
            <Link href="/projects" className="font-semibold text-[#173B35] hover:underline">
              browse all projects
            </Link>
            .
          </div>
        )}

        {!error && featured !== null && featured.length > 0 && (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
            {featured.map((project) => (
              <ProjectCard key={project.id} project={project} />
            ))}
          </div>
        )}
      </section>

      {/* About */}
      <section id="about" className="bg-white border-y border-[#E5E5DE]">
        <div className="max-w-4xl mx-auto px-4 md:px-8 py-16 text-center">
          <h2 className="font-heading font-bold text-2xl md:text-3xl text-[#202B28] tracking-tight">
            About Us
          </h2>
          <p className="text-base text-[#4F574F] mt-4 leading-relaxed">
            EstateFlow AI brings together our published residential projects, approved project
            information and sales team in one place -- so prospective buyers can explore with
            confidence before speaking with us directly.
          </p>
        </div>
      </section>

      {/* How It Works */}
      <section className="max-w-7xl mx-auto px-4 md:px-8 py-16">
        <h2 className="font-heading font-bold text-2xl md:text-3xl text-[#202B28] tracking-tight text-center">
          How It Works
        </h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6 mt-10">
          {JOURNEY_STEPS.map((step, index) => {
            const Icon = step.icon;
            return (
              <div
                key={step.title}
                className="bg-white rounded-xl border border-[#E5E5DE] p-6 shadow-xs text-center flex flex-col items-center"
              >
                <div className="w-11 h-11 rounded-full bg-[#E9F5EF] text-[#173B35] flex items-center justify-center mb-4">
                  <Icon className="w-5 h-5" aria-hidden="true" />
                </div>
                <span className="text-xs font-bold text-[#C47A55] uppercase tracking-wider">
                  Step {index + 1}
                </span>
                <h3 className="font-heading font-semibold text-base text-[#202B28] mt-1.5">
                  {step.title}
                </h3>
                <p className="text-sm text-[#737C76] mt-2 leading-relaxed">{step.description}</p>
              </div>
            );
          })}
        </div>
      </section>

      {/* Contact */}
      <section id="contact" className="max-w-4xl mx-auto px-4 md:px-8 py-16 text-center">
        <h2 className="font-heading font-bold text-2xl md:text-3xl text-[#202B28] tracking-tight">
          Contact Us
        </h2>
        <p className="text-base text-[#4F574F] mt-4 leading-relaxed">
          Verified phone, email and office details for this developer will be published here once
          confirmed. In the meantime, explore a project and reach out through its details page --
          our sales team will follow up directly.
        </p>
        <Link
          href="/projects"
          className="inline-flex items-center gap-2 mt-6 h-11 px-5 rounded-lg bg-[#173B35] hover:bg-[#1f4b43] text-white text-sm font-semibold transition-colors"
        >
          Explore Projects
          <ArrowRight className="w-4 h-4" />
        </Link>
      </section>
    </>
  );
}
