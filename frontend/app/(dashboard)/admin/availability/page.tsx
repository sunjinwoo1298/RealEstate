"use client";

import React, { useEffect, useState } from "react";
import { Ban, Plus, Settings2 } from "lucide-react";
import { useAuth } from "@/lib/auth-context";
import {
  apiClient,
  ApiError,
  AvailabilityRulePublic,
  BlockedPeriodPublic,
  ProjectPublic,
  ProjectVisitCapacityPublic,
} from "@/lib/api-client";

const DAY_LABELS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];

export default function AdminAvailabilityPage() {
  const { user } = useAuth();

  const [projects, setProjects] = useState<ProjectPublic[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState("");
  const [rules, setRules] = useState<AvailabilityRulePublic[]>([]);
  const [blockedPeriods, setBlockedPeriods] = useState<BlockedPeriodPublic[]>([]);
  const [capacity, setCapacity] = useState<ProjectVisitCapacityPublic | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [ruleForm, setRuleForm] = useState({ executive_id: "", day_of_week: "0", start_time: "09:00", end_time: "18:00" });
  const [blockForm, setBlockForm] = useState({ executive_id: "", start_time: "", end_time: "", reason: "" });
  const [capacityForm, setCapacityForm] = useState({ capacity: "1", visit_duration_minutes: "30", buffer_minutes: "0" });

  const loadProjects = async () => {
    try {
      const data = await apiClient.listProjects({});
      setProjects(data.items);
      if (!selectedProjectId && data.items.length > 0) setSelectedProjectId(data.items[0].id);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load projects.");
    }
  };

  const loadRules = async (projectId: string) => {
    try {
      const data = await apiClient.listAvailabilityRules({ project_id: projectId });
      setRules(data.items);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load availability rules.");
    }
  };

  const loadBlockedPeriods = async () => {
    try {
      const data = await apiClient.listBlockedPeriods();
      setBlockedPeriods(data);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load blocked periods.");
    }
  };

  const loadCapacity = async (projectId: string) => {
    try {
      const data = await apiClient.getVisitCapacity(projectId);
      setCapacity(data);
      setCapacityForm({
        capacity: String(data.capacity),
        visit_duration_minutes: String(data.visit_duration_minutes),
        buffer_minutes: String(data.buffer_minutes),
      });
    } catch {
      setCapacity(null);
    }
  };

  useEffect(() => {
    if (user && (user.role === "ADMIN" || user.role === "MANAGER")) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- intentional data fetch on mount
      loadProjects();
      // eslint-disable-next-line react-hooks/set-state-in-effect -- intentional data fetch on mount
      loadBlockedPeriods();
    }
  }, [user]);

  useEffect(() => {
    if (selectedProjectId) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- intentional data fetch on selection change
      loadRules(selectedProjectId);
      // eslint-disable-next-line react-hooks/set-state-in-effect -- intentional data fetch on selection change
      loadCapacity(selectedProjectId);
    }
  }, [selectedProjectId]);

  const handleCreateRule = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      await apiClient.createAvailabilityRule({
        executive_id: ruleForm.executive_id,
        project_id: selectedProjectId,
        day_of_week: Number(ruleForm.day_of_week),
        start_time: ruleForm.start_time,
        end_time: ruleForm.end_time,
      });
      setRuleForm({ ...ruleForm, executive_id: "" });
      await loadRules(selectedProjectId);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to create availability rule.");
    }
  };

  const handleDeleteRule = async (ruleId: string) => {
    try {
      await apiClient.deleteAvailabilityRule(ruleId);
      await loadRules(selectedProjectId);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to delete availability rule.");
    }
  };

  const handleCreateBlock = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      await apiClient.createBlockedPeriod({
        executive_id: blockForm.executive_id,
        start_time: new Date(blockForm.start_time).toISOString(),
        end_time: new Date(blockForm.end_time).toISOString(),
        reason: blockForm.reason || undefined,
      });
      setBlockForm({ executive_id: "", start_time: "", end_time: "", reason: "" });
      await loadBlockedPeriods();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to create blocked period.");
    }
  };

  const handleDeleteBlock = async (blockedPeriodId: string) => {
    try {
      await apiClient.deleteBlockedPeriod(blockedPeriodId);
      await loadBlockedPeriods();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to delete blocked period.");
    }
  };

  const handleSaveCapacity = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedProjectId) return;
    setError(null);
    try {
      const updated = await apiClient.upsertVisitCapacity({
        project_id: selectedProjectId,
        capacity: Number(capacityForm.capacity),
        visit_duration_minutes: Number(capacityForm.visit_duration_minutes),
        buffer_minutes: Number(capacityForm.buffer_minutes),
      });
      setCapacity(updated);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to save visit capacity.");
    }
  };

  if (!user || (user.role !== "ADMIN" && user.role !== "MANAGER")) {
    return <p className="text-sm text-[#737C76]">Only admins and managers can manage availability.</p>;
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold font-heading text-[#202B28] tracking-tight">Executive Availability</h1>
        <p className="text-sm text-[#737C76] mt-1">
          Configure working hours, blocked periods and site-visit capacity per project.
        </p>
      </div>

      {error && <p className="text-sm text-[#C34D4D]">{error}</p>}

      <div className="bg-white rounded-xl border border-[#E5E5DE] shadow-xs p-4 flex items-center gap-3">
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
      </div>

      <div className="bg-white rounded-xl border border-[#E5E5DE] shadow-xs p-6 space-y-4">
        <h2 className="text-sm font-semibold text-[#202B28] flex items-center gap-2">
          <Settings2 className="w-4 h-4 text-[#173B35]" /> Visit Capacity
        </h2>
        <form onSubmit={handleSaveCapacity} className="grid grid-cols-1 md:grid-cols-4 gap-4 items-end">
          <div>
            <label className="block text-xs font-semibold text-[#202B28] mb-1.5">Site capacity</label>
            <input
              type="number"
              min={1}
              value={capacityForm.capacity}
              onChange={(e) => setCapacityForm({ ...capacityForm, capacity: e.target.value })}
              className="w-full h-10 px-3 rounded-lg border border-[#E5E5DE] text-sm focus:outline-none focus:ring-2 focus:ring-[#315C50]"
            />
          </div>
          <div>
            <label className="block text-xs font-semibold text-[#202B28] mb-1.5">Visit duration (min)</label>
            <input
              type="number"
              min={1}
              value={capacityForm.visit_duration_minutes}
              onChange={(e) => setCapacityForm({ ...capacityForm, visit_duration_minutes: e.target.value })}
              className="w-full h-10 px-3 rounded-lg border border-[#E5E5DE] text-sm focus:outline-none focus:ring-2 focus:ring-[#315C50]"
            />
          </div>
          <div>
            <label className="block text-xs font-semibold text-[#202B28] mb-1.5">Buffer (min)</label>
            <input
              type="number"
              min={0}
              value={capacityForm.buffer_minutes}
              onChange={(e) => setCapacityForm({ ...capacityForm, buffer_minutes: e.target.value })}
              className="w-full h-10 px-3 rounded-lg border border-[#E5E5DE] text-sm focus:outline-none focus:ring-2 focus:ring-[#315C50]"
            />
          </div>
          <button
            type="submit"
            disabled={!selectedProjectId}
            className="h-10 px-4 rounded-lg bg-[#315C50] hover:bg-[#3c6e60] disabled:opacity-60 text-white text-sm font-semibold"
          >
            {capacity ? "Update" : "Configure"}
          </button>
        </form>
      </div>

      <div className="bg-white rounded-xl border border-[#E5E5DE] shadow-xs p-6 space-y-4">
        <h2 className="text-sm font-semibold text-[#202B28] flex items-center gap-2">
          <Plus className="w-4 h-4 text-[#173B35]" /> Working Hours
        </h2>
        <form onSubmit={handleCreateRule} className="grid grid-cols-1 md:grid-cols-5 gap-4 items-end">
          <div>
            <label className="block text-xs font-semibold text-[#202B28] mb-1.5">Executive ID</label>
            <input
              required
              value={ruleForm.executive_id}
              onChange={(e) => setRuleForm({ ...ruleForm, executive_id: e.target.value })}
              className="w-full h-10 px-3 rounded-lg border border-[#E5E5DE] text-sm focus:outline-none focus:ring-2 focus:ring-[#315C50]"
              placeholder="User UUID"
            />
          </div>
          <div>
            <label className="block text-xs font-semibold text-[#202B28] mb-1.5">Day</label>
            <select
              value={ruleForm.day_of_week}
              onChange={(e) => setRuleForm({ ...ruleForm, day_of_week: e.target.value })}
              className="w-full h-10 px-3 rounded-lg border border-[#E5E5DE] text-sm bg-white focus:outline-none focus:ring-2 focus:ring-[#315C50]"
            >
              {DAY_LABELS.map((label, idx) => (
                <option key={label} value={idx}>
                  {label}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-xs font-semibold text-[#202B28] mb-1.5">Start</label>
            <input
              type="time"
              value={ruleForm.start_time}
              onChange={(e) => setRuleForm({ ...ruleForm, start_time: e.target.value })}
              className="w-full h-10 px-3 rounded-lg border border-[#E5E5DE] text-sm focus:outline-none focus:ring-2 focus:ring-[#315C50]"
            />
          </div>
          <div>
            <label className="block text-xs font-semibold text-[#202B28] mb-1.5">End</label>
            <input
              type="time"
              value={ruleForm.end_time}
              onChange={(e) => setRuleForm({ ...ruleForm, end_time: e.target.value })}
              className="w-full h-10 px-3 rounded-lg border border-[#E5E5DE] text-sm focus:outline-none focus:ring-2 focus:ring-[#315C50]"
            />
          </div>
          <button
            type="submit"
            disabled={!selectedProjectId}
            className="h-10 px-4 rounded-lg bg-[#315C50] hover:bg-[#3c6e60] disabled:opacity-60 text-white text-sm font-semibold"
          >
            Add Rule
          </button>
        </form>

        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs font-semibold text-[#737C76] uppercase tracking-wider border-b border-[#E5E5DE]">
              <th className="px-3 py-2">Executive</th>
              <th className="px-3 py-2">Day</th>
              <th className="px-3 py-2">Hours (IST)</th>
              <th className="px-3 py-2 text-right">Actions</th>
            </tr>
          </thead>
          <tbody>
            {rules.map((rule) => (
              <tr key={rule.id} className="border-b border-[#F0F1EC] last:border-0">
                <td className="px-3 py-2 text-[#202B28] font-mono text-xs">{rule.executive_id.slice(0, 8)}...</td>
                <td className="px-3 py-2 text-[#737C76]">{DAY_LABELS[rule.day_of_week]}</td>
                <td className="px-3 py-2 text-[#737C76]">
                  {rule.start_time.slice(0, 5)} - {rule.end_time.slice(0, 5)}
                </td>
                <td className="px-3 py-2 text-right">
                  <button
                    onClick={() => handleDeleteRule(rule.id)}
                    className="text-xs font-semibold text-[#C34D4D] hover:underline"
                  >
                    Remove
                  </button>
                </td>
              </tr>
            ))}
            {rules.length === 0 && (
              <tr>
                <td colSpan={4} className="px-3 py-6 text-center text-sm text-[#737C76]">
                  No rules configured for this project.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="bg-white rounded-xl border border-[#E5E5DE] shadow-xs p-6 space-y-4">
        <h2 className="text-sm font-semibold text-[#202B28] flex items-center gap-2">
          <Ban className="w-4 h-4 text-[#173B35]" /> Blocked Periods (Leave / Breaks)
        </h2>
        <form onSubmit={handleCreateBlock} className="grid grid-cols-1 md:grid-cols-5 gap-4 items-end">
          <div>
            <label className="block text-xs font-semibold text-[#202B28] mb-1.5">Executive ID</label>
            <input
              required
              value={blockForm.executive_id}
              onChange={(e) => setBlockForm({ ...blockForm, executive_id: e.target.value })}
              className="w-full h-10 px-3 rounded-lg border border-[#E5E5DE] text-sm focus:outline-none focus:ring-2 focus:ring-[#315C50]"
              placeholder="User UUID"
            />
          </div>
          <div>
            <label className="block text-xs font-semibold text-[#202B28] mb-1.5">Start</label>
            <input
              required
              type="datetime-local"
              value={blockForm.start_time}
              onChange={(e) => setBlockForm({ ...blockForm, start_time: e.target.value })}
              className="w-full h-10 px-3 rounded-lg border border-[#E5E5DE] text-sm focus:outline-none focus:ring-2 focus:ring-[#315C50]"
            />
          </div>
          <div>
            <label className="block text-xs font-semibold text-[#202B28] mb-1.5">End</label>
            <input
              required
              type="datetime-local"
              value={blockForm.end_time}
              onChange={(e) => setBlockForm({ ...blockForm, end_time: e.target.value })}
              className="w-full h-10 px-3 rounded-lg border border-[#E5E5DE] text-sm focus:outline-none focus:ring-2 focus:ring-[#315C50]"
            />
          </div>
          <div>
            <label className="block text-xs font-semibold text-[#202B28] mb-1.5">Reason</label>
            <input
              value={blockForm.reason}
              onChange={(e) => setBlockForm({ ...blockForm, reason: e.target.value })}
              className="w-full h-10 px-3 rounded-lg border border-[#E5E5DE] text-sm focus:outline-none focus:ring-2 focus:ring-[#315C50]"
            />
          </div>
          <button
            type="submit"
            className="h-10 px-4 rounded-lg bg-[#C47A55] hover:bg-[#b56a46] text-white text-sm font-semibold"
          >
            Block
          </button>
        </form>

        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs font-semibold text-[#737C76] uppercase tracking-wider border-b border-[#E5E5DE]">
              <th className="px-3 py-2">Executive</th>
              <th className="px-3 py-2">From</th>
              <th className="px-3 py-2">To</th>
              <th className="px-3 py-2">Reason</th>
              <th className="px-3 py-2 text-right">Actions</th>
            </tr>
          </thead>
          <tbody>
            {blockedPeriods.map((bp) => (
              <tr key={bp.id} className="border-b border-[#F0F1EC] last:border-0">
                <td className="px-3 py-2 text-[#202B28] font-mono text-xs">{bp.executive_id.slice(0, 8)}...</td>
                <td className="px-3 py-2 text-[#737C76]">{new Date(bp.start_time).toLocaleString("en-IN", { timeZone: "Asia/Kolkata" })}</td>
                <td className="px-3 py-2 text-[#737C76]">{new Date(bp.end_time).toLocaleString("en-IN", { timeZone: "Asia/Kolkata" })}</td>
                <td className="px-3 py-2 text-[#737C76]">{bp.reason || "-"}</td>
                <td className="px-3 py-2 text-right">
                  <button
                    onClick={() => handleDeleteBlock(bp.id)}
                    className="text-xs font-semibold text-[#C34D4D] hover:underline"
                  >
                    Remove
                  </button>
                </td>
              </tr>
            ))}
            {blockedPeriods.length === 0 && (
              <tr>
                <td colSpan={5} className="px-3 py-6 text-center text-sm text-[#737C76]">
                  No blocked periods.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
