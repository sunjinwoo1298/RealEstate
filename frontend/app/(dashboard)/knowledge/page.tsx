"use client";

import React, { useEffect, useState } from "react";
import { Plus, Upload, FileText, CheckCircle2, Archive, Loader2 } from "lucide-react";
import { useAuth } from "@/lib/auth-context";
import {
  apiClient,
  ApiError,
  ProjectPublic,
  KnowledgeDocumentPublic,
  ApprovalStatus,
} from "@/lib/api-client";

const STATUS_BADGE: Record<ApprovalStatus, string> = {
  DRAFT: "bg-[#F0F1EC] text-[#202B28]",
  APPROVED: "bg-[#E9F5EF] text-[#27845B]",
  ARCHIVED: "bg-[#FDF2F2] text-[#C34D4D]",
};

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
