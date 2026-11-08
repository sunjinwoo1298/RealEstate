"use client";

import React, { useEffect, useState } from "react";
import { Plus, Upload, FileText, CheckCircle2, Archive, Loader2, Globe, Star } from "lucide-react";
import { useAuth } from "@/lib/auth-context";
import {
  apiClient,
  ApiError,
  ProjectPublic,
  ProjectVisibility,
  KnowledgeDocumentPublic,
  ApprovalStatus,
} from "@/lib/api-client";

const STATUS_BADGE: Record<ApprovalStatus, string> = {
  DRAFT: "bg-[#F0F1EC] text-[#202B28]",
  APPROVED: "bg-[#E9F5EF] text-[#27845B]",
  ARCHIVED: "bg-[#FDF2F2] text-[#C34D4D]",
};

const VISIBILITY_BADGE: Record<ProjectVisibility, string> = {
  DRAFT: "bg-[#F0F1EC] text-[#202B28]",
  PUBLISHED: "bg-[#E9F5EF] text-[#27845B]",
  ARCHIVED: "bg-[#FDF2F2] text-[#C34D4D]",
};

const linesToList = (value: string): string[] =>
  value
    .split(/\r?\n|,/)
    .map((v) => v.trim())
    .filter((v) => v.length > 0);

export default function KnowledgeBasePage() {
  const { user } = useAuth();

  const [projects, setProjects] = useState<ProjectPublic[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState<string>("");
  const [documents, setDocuments] = useState<KnowledgeDocumentPublic[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [showProjectForm, setShowProjectForm] = useState(false);
  const [projectForm, setProjectForm] = useState({ name: "", description: "", location: "" });
  const [projectSubmitting, setProjectSubmitting] = useState(false);

  const [showUploadForm, setShowUploadForm] = useState(false);
  const [uploadTitle, setUploadTitle] = useState("");
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploadSubmitting, setUploadSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const selectedProject = projects.find((p) => p.id === selectedProjectId) ?? null;

  const [publicForm, setPublicForm] = useState({
    configurations: "",
    amenities: "",
    images: "",
    starting_price_label: "",
    price_display_approved: false,
    rera_number: "",
    floor_plan_url: "",
    is_featured: false,
  });
  const [publicFormSubmitting, setPublicFormSubmitting] = useState(false);
  const [publicFormError, setPublicFormError] = useState<string | null>(null);
  const [visibilityUpdating, setVisibilityUpdating] = useState(false);

  const loadProjects = async () => {
    try {
      const data = await apiClient.listProjects({});
      setProjects(data.items);
      if (!selectedProjectId && data.items.length > 0) {
        setSelectedProjectId(data.items[0].id);
      }
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load projects.");
    }
  };

  const loadDocuments = async (projectId: string) => {
    setLoading(true);
    try {
      const data = await apiClient.listKnowledgeDocuments(projectId);
      setDocuments(data.items);
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load knowledge documents.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (user?.role === "ADMIN") {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- intentional data fetch on mount
      loadProjects();
    }
  }, [user]);

  useEffect(() => {
    if (selectedProjectId) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- intentional data fetch on selection change
      loadDocuments(selectedProjectId);
    } else {
      setLoading(false);
    }
  }, [selectedProjectId]);

  useEffect(() => {
    if (!selectedProject) return;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- intentional form reset on selection change
    setPublicForm({
      configurations: (selectedProject.configurations ?? []).join(", "),
      amenities: (selectedProject.amenities ?? []).join(", "),
      images: (selectedProject.images ?? []).join("\n"),
      starting_price_label: selectedProject.starting_price_label ?? "",
      price_display_approved: selectedProject.price_display_approved,
      rera_number: selectedProject.rera_number ?? "",
      floor_plan_url: selectedProject.floor_plan_url ?? "",
      is_featured: selectedProject.is_featured,
    });
    setPublicFormError(null);
  }, [selectedProjectId, selectedProject]);

  const handleCreateProject = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError(null);
    setProjectSubmitting(true);
    try {
      const created = await apiClient.createProject({
        name: projectForm.name,
        description: projectForm.description || undefined,
        location: projectForm.location || undefined,
      });
      setProjectForm({ name: "", description: "", location: "" });
      setShowProjectForm(false);
      await loadProjects();
      setSelectedProjectId(created.id);
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : "Failed to create project.");
    } finally {
      setProjectSubmitting(false);
    }
  };

  const handleUpload = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!uploadFile || !selectedProjectId) return;
    setFormError(null);
    setUploadSubmitting(true);
    try {
      await apiClient.uploadKnowledgeDocument({
        project_id: selectedProjectId,
        title: uploadTitle,
        file: uploadFile,
      });
      setUploadTitle("");
      setUploadFile(null);
      setShowUploadForm(false);
      await loadDocuments(selectedProjectId);
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : "Failed to upload document.");
    } finally {
      setUploadSubmitting(false);
    }
  };

  const handleApprove = async (documentId: string) => {
    try {
      await apiClient.approveKnowledgeDocument(documentId);
      await loadDocuments(selectedProjectId);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to approve document.");
    }
  };

  const handleArchive = async (documentId: string) => {
    try {
      await apiClient.archiveKnowledgeDocument(documentId);
      await loadDocuments(selectedProjectId);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to archive document.");
    }
  };

  const handleVisibilityChange = async (status: ProjectVisibility) => {
    if (!selectedProjectId) return;
    setVisibilityUpdating(true);
    setPublicFormError(null);
    try {
      await apiClient.updateProject(selectedProjectId, { visibility_status: status });
      await loadProjects();
    } catch (err) {
      setPublicFormError(err instanceof ApiError ? err.message : "Failed to update publication status.");
    } finally {
      setVisibilityUpdating(false);
    }
  };

  const handleSavePublicListing = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedProjectId) return;
    setPublicFormSubmitting(true);
    setPublicFormError(null);
    try {
      await apiClient.updateProject(selectedProjectId, {
        configurations: linesToList(publicForm.configurations),
        amenities: linesToList(publicForm.amenities),
        images: linesToList(publicForm.images),
        starting_price_label: publicForm.starting_price_label || "",
        price_display_approved: publicForm.price_display_approved,
        rera_number: publicForm.rera_number || "",
        floor_plan_url: publicForm.floor_plan_url || "",
        is_featured: publicForm.is_featured,
      });
      await loadProjects();
    } catch (err) {
      setPublicFormError(err instanceof ApiError ? err.message : "Failed to save public listing.");
    } finally {
      setPublicFormSubmitting(false);
    }
  };

  if (!user || user.role !== "ADMIN") {
    return <p className="text-sm text-[#737C76]">Only admins can manage the knowledge base.</p>;
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold font-heading text-[#202B28] tracking-tight">Knowledge Base</h1>
          <p className="text-sm text-[#737C76] mt-1">
            Manage project fact sheets. Only APPROVED documents can ground AI responses.
          </p>
        </div>
        <button
          onClick={() => setShowProjectForm((v) => !v)}
          className="h-10 px-4 rounded-lg bg-[#173B35] hover:bg-[#1f4b43] text-white text-sm font-semibold flex items-center gap-2 transition-colors"
        >
          <Plus className="w-4 h-4" />
          New Project
        </button>
      </div>

      {showProjectForm && (
        <form
          onSubmit={handleCreateProject}
          className="bg-white rounded-xl border border-[#E5E5DE] shadow-xs p-6 grid grid-cols-1 md:grid-cols-3 gap-4 items-end"
        >
          <div>
            <label className="block text-xs font-semibold text-[#202B28] mb-1.5">Project name</label>
            <input
              required
              value={projectForm.name}
              onChange={(e) => setProjectForm({ ...projectForm, name: e.target.value })}
              className="w-full h-10 px-3 rounded-lg border border-[#E5E5DE] text-sm focus:outline-none focus:ring-2 focus:ring-[#315C50]"
            />
          </div>
          <div>
            <label className="block text-xs font-semibold text-[#202B28] mb-1.5">Location</label>
            <input
              value={projectForm.location}
              onChange={(e) => setProjectForm({ ...projectForm, location: e.target.value })}
              className="w-full h-10 px-3 rounded-lg border border-[#E5E5DE] text-sm focus:outline-none focus:ring-2 focus:ring-[#315C50]"
            />
          </div>
          <div>
            <label className="block text-xs font-semibold text-[#202B28] mb-1.5">Description</label>
            <input
              value={projectForm.description}
              onChange={(e) => setProjectForm({ ...projectForm, description: e.target.value })}
              className="w-full h-10 px-3 rounded-lg border border-[#E5E5DE] text-sm focus:outline-none focus:ring-2 focus:ring-[#315C50]"
            />
          </div>
          {formError && <p className="md:col-span-3 text-sm text-[#C34D4D]">{formError}</p>}
          <div className="md:col-span-3">
            <button
              type="submit"
              disabled={projectSubmitting}
              className="h-10 px-4 rounded-lg bg-[#315C50] hover:bg-[#3c6e60] disabled:opacity-60 text-white text-sm font-semibold flex items-center gap-2"
            >
              {projectSubmitting && <Loader2 className="w-4 h-4 animate-spin" />}
              Create project
            </button>
          </div>
        </form>
      )}

      <div className="bg-white rounded-xl border border-[#E5E5DE] shadow-xs p-4 flex flex-wrap items-center gap-3">
        <label className="text-xs font-semibold text-[#202B28]">Project:</label>
        <select
          value={selectedProjectId}
          onChange={(e) => setSelectedProjectId(e.target.value)}
          className="h-10 px-3 rounded-lg border border-[#E5E5DE] text-sm bg-white focus:outline-none focus:ring-2 focus:ring-[#315C50]"
        >
          {projects.length === 0 && <option value="">No projects yet</option>}
          {projects.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </select>

        {selectedProjectId && (
          <button
            onClick={() => setShowUploadForm((v) => !v)}
            className="h-10 px-4 rounded-lg bg-[#C47A55] hover:bg-[#b56a46] text-white text-sm font-semibold flex items-center gap-2 transition-colors ml-auto"
          >
            <Upload className="w-4 h-4" />
            Upload Fact Sheet
          </button>
        )}
      </div>

      {selectedProject && (
        <div className="bg-white rounded-xl border border-[#E5E5DE] shadow-xs overflow-hidden">
          <div className="px-6 py-4 border-b border-[#E5E5DE] flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <Globe className="w-4 h-4 text-[#173B35]" />
              <h2 className="text-sm font-semibold text-[#202B28]">Public Website Listing</h2>
              <span
                className={`text-xs font-semibold px-2 py-1 rounded-md ${VISIBILITY_BADGE[selectedProject.visibility_status]}`}
              >
                {selectedProject.visibility_status}
              </span>
            </div>
            <div className="flex items-center gap-2">
              {selectedProject.visibility_status !== "PUBLISHED" && (
                <button
                  type="button"
                  disabled={visibilityUpdating}
                  onClick={() => handleVisibilityChange("PUBLISHED")}
                  className="h-9 px-3 rounded-lg bg-[#27845B] hover:bg-[#206e4b] disabled:opacity-60 text-white text-xs font-semibold transition-colors"
                >
                  Publish
                </button>
              )}
              {selectedProject.visibility_status === "PUBLISHED" && (
                <button
                  type="button"
                  disabled={visibilityUpdating}
                  onClick={() => handleVisibilityChange("DRAFT")}
                  className="h-9 px-3 rounded-lg border border-[#E5E5DE] hover:bg-[#F0F1EC] disabled:opacity-60 text-xs font-semibold text-[#202B28] transition-colors"
                >
                  Unpublish to Draft
                </button>
              )}
              {selectedProject.visibility_status !== "ARCHIVED" && (
                <button
                  type="button"
                  disabled={visibilityUpdating}
                  onClick={() => handleVisibilityChange("ARCHIVED")}
                  className="h-9 px-3 rounded-lg border border-[#F8D2D2] text-[#C34D4D] hover:bg-[#FDF2F2] disabled:opacity-60 text-xs font-semibold transition-colors"
                >
                  Archive
                </button>
              )}
            </div>
          </div>

          <form onSubmit={handleSavePublicListing} className="p-6 grid grid-cols-1 md:grid-cols-2 gap-4">
            <label className="flex items-center gap-2 md:col-span-2 text-sm font-medium text-[#202B28]">
              <input
                type="checkbox"
                checked={publicForm.is_featured}
                onChange={(e) => setPublicForm({ ...publicForm, is_featured: e.target.checked })}
                className="w-4 h-4 accent-[#173B35]"
              />
              <Star className="w-4 h-4 text-[#C47A55]" />
              Show on homepage as a featured project
            </label>

            <div>
              <label className="block text-xs font-semibold text-[#202B28] mb-1.5">
                Configurations (comma-separated)
              </label>
              <input
                value={publicForm.configurations}
                onChange={(e) => setPublicForm({ ...publicForm, configurations: e.target.value })}
                placeholder="2 BHK, 3 BHK"
                className="w-full h-10 px-3 rounded-lg border border-[#E5E5DE] text-sm focus:outline-none focus:ring-2 focus:ring-[#315C50]"
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-[#202B28] mb-1.5">
                Amenities (comma-separated)
              </label>
              <input
                value={publicForm.amenities}
                onChange={(e) => setPublicForm({ ...publicForm, amenities: e.target.value })}
                placeholder="Gymnasium, Rooftop Garden"
                className="w-full h-10 px-3 rounded-lg border border-[#E5E5DE] text-sm focus:outline-none focus:ring-2 focus:ring-[#315C50]"
              />
            </div>

            <div className="md:col-span-2">
              <label className="block text-xs font-semibold text-[#202B28] mb-1.5">
                Image URLs (one per line -- first is used as the primary/hero image)
              </label>
              <textarea
                value={publicForm.images}
                onChange={(e) => setPublicForm({ ...publicForm, images: e.target.value })}
                rows={3}
                placeholder="https://..."
                className="w-full px-3 py-2 rounded-lg border border-[#E5E5DE] text-sm focus:outline-none focus:ring-2 focus:ring-[#315C50]"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold text-[#202B28] mb-1.5">
                Starting price label
              </label>
              <input
                value={publicForm.starting_price_label}
                onChange={(e) => setPublicForm({ ...publicForm, starting_price_label: e.target.value })}
                placeholder="Starting at Rs. 85 Lakh"
                className="w-full h-10 px-3 rounded-lg border border-[#E5E5DE] text-sm focus:outline-none focus:ring-2 focus:ring-[#315C50]"
              />
              <label className="flex items-center gap-2 mt-2 text-xs text-[#737C76]">
                <input
                  type="checkbox"
                  checked={publicForm.price_display_approved}
                  onChange={(e) => setPublicForm({ ...publicForm, price_display_approved: e.target.checked })}
                  className="w-3.5 h-3.5 accent-[#173B35]"
                />
                Approved for public display (required for the price to appear on the website)
              </label>
            </div>
            <div>
              <label className="block text-xs font-semibold text-[#202B28] mb-1.5">RERA number</label>
              <input
                value={publicForm.rera_number}
                onChange={(e) => setPublicForm({ ...publicForm, rera_number: e.target.value })}
                className="w-full h-10 px-3 rounded-lg border border-[#E5E5DE] text-sm focus:outline-none focus:ring-2 focus:ring-[#315C50]"
              />
            </div>

            <div className="md:col-span-2">
              <label className="block text-xs font-semibold text-[#202B28] mb-1.5">
                Floor plan / brochure URL (only set once approved for public access)
              </label>
              <input
                value={publicForm.floor_plan_url}
                onChange={(e) => setPublicForm({ ...publicForm, floor_plan_url: e.target.value })}
                placeholder="https://..."
                className="w-full h-10 px-3 rounded-lg border border-[#E5E5DE] text-sm focus:outline-none focus:ring-2 focus:ring-[#315C50]"
              />
            </div>

            {publicFormError && <p className="md:col-span-2 text-sm text-[#C34D4D]">{publicFormError}</p>}

            <div className="md:col-span-2">
              <button
                type="submit"
                disabled={publicFormSubmitting}
                className="h-10 px-4 rounded-lg bg-[#173B35] hover:bg-[#1f4b43] disabled:opacity-60 text-white text-sm font-semibold flex items-center gap-2"
              >
                {publicFormSubmitting && <Loader2 className="w-4 h-4 animate-spin" />}
                Save public listing
              </button>
            </div>
          </form>
        </div>
      )}

      {showUploadForm && selectedProjectId && (
        <form
          onSubmit={handleUpload}
          className="bg-white rounded-xl border border-[#E5E5DE] shadow-xs p-6 grid grid-cols-1 md:grid-cols-3 gap-4 items-end"
        >
          <div>
            <label className="block text-xs font-semibold text-[#202B28] mb-1.5">Document title</label>
            <input
              required
              value={uploadTitle}
              onChange={(e) => setUploadTitle(e.target.value)}
              className="w-full h-10 px-3 rounded-lg border border-[#E5E5DE] text-sm focus:outline-none focus:ring-2 focus:ring-[#315C50]"
              placeholder="e.g. Fact Sheet"
            />
          </div>
          <div>
            <label className="block text-xs font-semibold text-[#202B28] mb-1.5">File (PDF or .txt/.md)</label>
            <input
              required
              type="file"
              accept=".pdf,.txt,.md"
              onChange={(e) => setUploadFile(e.target.files?.[0] ?? null)}
              className="w-full text-sm"
            />
          </div>
          {formError && <p className="md:col-span-3 text-sm text-[#C34D4D]">{formError}</p>}
          <div className="md:col-span-3">
            <button
              type="submit"
              disabled={uploadSubmitting}
              className="h-10 px-4 rounded-lg bg-[#315C50] hover:bg-[#3c6e60] disabled:opacity-60 text-white text-sm font-semibold flex items-center gap-2"
            >
              {uploadSubmitting && <Loader2 className="w-4 h-4 animate-spin" />}
              Upload as new draft version
            </button>
          </div>
        </form>
      )}

      <div className="bg-white rounded-xl border border-[#E5E5DE] shadow-xs overflow-hidden">
        <div className="px-6 py-4 border-b border-[#E5E5DE] flex items-center gap-2">
          <FileText className="w-4 h-4 text-[#173B35]" />
          <h2 className="text-sm font-semibold text-[#202B28]">Fact sheet versions</h2>
        </div>

        {error && <p className="px-6 py-4 text-sm text-[#C34D4D]">{error}</p>}

        {loading ? (
          <div className="px-6 py-8 text-center text-sm text-[#737C76]">Loading...</div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs font-semibold text-[#737C76] uppercase tracking-wider border-b border-[#E5E5DE]">
                <th className="px-6 py-3">Title</th>
                <th className="px-6 py-3">Version</th>
                <th className="px-6 py-3">Status</th>
                <th className="px-6 py-3">Chunks</th>
                <th className="px-6 py-3">Uploaded</th>
                <th className="px-6 py-3 text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {documents.map((doc) => (
                <tr key={doc.id} className="border-b border-[#F0F1EC] last:border-0">
                  <td className="px-6 py-3 font-medium text-[#202B28]">{doc.title}</td>
                  <td className="px-6 py-3 text-[#737C76]">v{doc.version}</td>
                  <td className="px-6 py-3">
                    <span className={`text-xs font-semibold px-2 py-1 rounded-md ${STATUS_BADGE[doc.approval_status]}`}>
                      {doc.approval_status}
                    </span>
                  </td>
                  <td className="px-6 py-3 text-[#737C76]">{doc.chunk_count}</td>
                  <td className="px-6 py-3 text-[#737C76]">{new Date(doc.created_at).toLocaleDateString()}</td>
                  <td className="px-6 py-3 text-right space-x-3">
                    {doc.approval_status === "DRAFT" && (
                      <button
                        onClick={() => handleApprove(doc.id)}
                        className="text-xs font-semibold text-[#27845B] hover:underline inline-flex items-center gap-1"
                      >
                        <CheckCircle2 className="w-3.5 h-3.5" />
                        Approve
                      </button>
                    )}
                    {doc.approval_status !== "ARCHIVED" && (
                      <button
                        onClick={() => handleArchive(doc.id)}
                        className="text-xs font-semibold text-[#C34D4D] hover:underline inline-flex items-center gap-1"
                      >
                        <Archive className="w-3.5 h-3.5" />
                        Archive
                      </button>
                    )}
                  </td>
                </tr>
              ))}
              {documents.length === 0 && (
                <tr>
                  <td colSpan={6} className="px-6 py-8 text-center text-sm text-[#737C76]">
                    No documents uploaded for this project yet.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
