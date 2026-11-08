import Link from "next/link";
import { Building2 } from "lucide-react";

export function PublicFooter() {
  return (
    <footer className="bg-[#142F2B] text-[#D1DDD7] mt-16">
      <div className="max-w-7xl mx-auto px-4 md:px-8 py-12 grid grid-cols-1 md:grid-cols-4 gap-10">
        <div>
          <div className="flex items-center gap-2.5">
            <div className="w-9 h-9 rounded-lg bg-[#C47A55] flex items-center justify-center shrink-0">
              <Building2 className="w-5 h-5 text-white" />
            </div>
            <span className="font-heading font-bold text-base text-white tracking-tight">
              EstateFlow <span className="text-[#C47A55]">AI</span>
            </span>
          </div>
          <p className="text-sm mt-4 leading-relaxed text-[#A3B8B0]">
            A residential property developer&apos;s platform for exploring thoughtfully designed
            projects and getting the information buyers need to make a confident decision.
          </p>
        </div>

        <div>
          <h3 className="text-xs font-semibold uppercase tracking-wider text-white mb-4">Navigate</h3>
          <ul className="space-y-2.5 text-sm">
            <li><Link href="/" className="hover:text-white transition-colors">Home</Link></li>
            <li><Link href="/projects" className="hover:text-white transition-colors">Explore Projects</Link></li>
            <li><Link href="/#about" className="hover:text-white transition-colors">About Us</Link></li>
            <li><Link href="/login" className="hover:text-white transition-colors">Staff Sign In</Link></li>
          </ul>
        </div>

        <div>
          <h3 className="text-xs font-semibold uppercase tracking-wider text-white mb-4">Contact</h3>
          <p className="text-sm text-[#A3B8B0] leading-relaxed">
            Verified contact details for this developer will appear here once published. For any
            project-specific query, our team will confirm details directly during a site visit or
            consultation.
          </p>
        </div>

        <div>
          <h3 className="text-xs font-semibold uppercase tracking-wider text-white mb-4">Legal</h3>
          <ul className="space-y-2.5 text-sm">
            <li><Link href="/privacy" className="hover:text-white transition-colors">Privacy Policy</Link></li>
            <li><Link href="/terms" className="hover:text-white transition-colors">Terms &amp; Conditions</Link></li>
          </ul>
          <p className="text-xs text-[#7E9A91] mt-4 leading-relaxed">
            RERA registration details for individual projects, where available, are shown on each
            project&apos;s own page.
          </p>
        </div>
      </div>

      <div className="border-t border-[#1b3d37] px-4 md:px-8 py-5 text-xs text-[#7E9A91] text-center">
        &copy; {new Date().getFullYear()} EstateFlow AI. All rights reserved.
      </div>
    </footer>
  );
}
