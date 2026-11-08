import Link from "next/link";
import { MapPin, Layers, ArrowRight, Image as ImageIcon } from "lucide-react";
import { PublicProjectCard as PublicProjectCardType } from "@/lib/api-client";

export function ProjectCard({ project }: { project: PublicProjectCardType }) {
  return (
    <article className="bg-white rounded-xl border border-[#E5E5DE] shadow-xs overflow-hidden flex flex-col hover:shadow-md transition-shadow">
      <div className="h-48 bg-[#F0F1EC] relative overflow-hidden">
        {project.primary_image ? (
          // eslint-disable-next-line @next/next/no-img-element -- external, admin-supplied URLs; no image-loader config
          <img
            src={project.primary_image}
            alt={`Exterior or rendering of ${project.name}`}
            className="w-full h-full object-cover"
          />
        ) : (
          <div className="w-full h-full flex items-center justify-center text-[#9FAAA4]">
            <ImageIcon className="w-10 h-10" aria-hidden="true" />
          </div>
        )}
        {project.is_featured && (
          <span className="absolute top-3 left-3 text-[11px] font-semibold uppercase tracking-wider px-2.5 py-1 rounded-md bg-[#C47A55] text-white shadow-sm">
            Featured
          </span>
        )}
      </div>

      <div className="p-5 flex flex-col flex-1">
        <h3 className="font-heading font-bold text-lg text-[#202B28] tracking-tight">
          {project.name}
        </h3>
        {project.location && (
          <p className="flex items-center gap-1.5 text-sm text-[#737C76] mt-1">
            <MapPin className="w-3.5 h-3.5 shrink-0" aria-hidden="true" />
            {project.location}
          </p>
        )}
        {project.description && (
          <p className="text-sm text-[#4F574F] mt-3 line-clamp-2">{project.description}</p>
        )}

        {project.configurations.length > 0 && (
          <p className="flex items-center gap-1.5 text-xs text-[#315C50] mt-3 font-medium">
            <Layers className="w-3.5 h-3.5 shrink-0" aria-hidden="true" />
            {project.configurations.join(" • ")}
          </p>
        )}

        <div className="flex items-center justify-between mt-4 pt-4 border-t border-[#F0F1EC]">
          <span className="text-sm font-semibold text-[#202B28]">
            {project.starting_price_label ?? "Price on request"}
          </span>
          <Link
            href={`/projects/${project.id}`}
            className="inline-flex items-center gap-1 text-sm font-semibold text-[#173B35] hover:text-[#C47A55] transition-colors"
          >
            View Details
            <ArrowRight className="w-3.5 h-3.5" aria-hidden="true" />
          </Link>
        </div>
      </div>
    </article>
  );
}
