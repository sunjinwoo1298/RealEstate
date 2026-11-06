"use client";

import React, { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Plus, ShieldAlert, Loader2, UserCog } from "lucide-react";
import { useAuth } from "@/lib/auth-context";
import { apiClient, ApiError, UserPublic, UserRole } from "@/lib/api-client";

const ROLE_OPTIONS: UserRole[] = ["ADMIN", "MANAGER", "SALES_EXECUTIVE"];

export default function StaffAccountsPage() {
  const { user } = useAuth();
  const router = useRouter();

  const [staff, setStaff] = useState<UserPublic[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [showCreateForm, setShowCreateForm] = useState(false);
  const [form, setForm] = useState({ email: "", full_name: "", password: "", role: "SALES_EXECUTIVE" as UserRole });
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  useEffect(() => {
    if (user && user.role !== "ADMIN") {
      router.replace("/");
    }
  }, [user, router]);

  const loadStaff = async () => {
    setLoading(true);
    try {
      const data = await apiClient.listStaffUsers();
      setStaff(data.items);
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load staff accounts.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (user?.role === "ADMIN") {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- intentional data fetch on mount
      loadStaff();
    }
  }, [user]);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError(null);
    setSubmitting(true);
    try {
      await apiClient.createStaffUser(form);
      setForm({ email: "", full_name: "", password: "", role: "SALES_EXECUTIVE" });
      setShowCreateForm(false);
      await loadStaff();
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : "Failed to create staff account.");
    } finally {
      setSubmitting(false);
    }
  };

  const toggleActive = async (member: UserPublic) => {
    try {
      await apiClient.updateStaffUserStatus(member.id, !member.is_active);
      await loadStaff();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to update staff account.");
    }
  };

  if (!user || user.role !== "ADMIN") {
    return (
      <div className="flex items-center gap-2 text-sm text-[#737C76]">
        <ShieldAlert className="w-4 h-4" />
        Redirecting...
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold font-heading text-[#202B28] tracking-tight">
            Staff Accounts
          </h1>
          <p className="text-sm text-[#737C76] mt-1">
            Create, update and deactivate admin, manager and sales executive accounts.
          </p>
        </div>
        <button
          onClick={() => setShowCreateForm((v) => !v)}
          className="h-10 px-4 rounded-lg bg-[#173B35] hover:bg-[#1f4b43] text-white text-sm font-semibold flex items-center gap-2 transition-colors"
        >
          <Plus className="w-4 h-4" />
          New Staff Account
        </button>
      </div>

      {showCreateForm && (
        <form
          onSubmit={handleCreate}
          className="bg-white rounded-xl border border-[#E5E5DE] shadow-xs p-6 grid grid-cols-1 md:grid-cols-4 gap-4 items-end"
        >
          <div>
            <label className="block text-xs font-semibold text-[#202B28] mb-1.5">Full name</label>
            <input
              required
              value={form.full_name}
              onChange={(e) => setForm({ ...form, full_name: e.target.value })}
              className="w-full h-10 px-3 rounded-lg border border-[#E5E5DE] text-sm focus:outline-none focus:ring-2 focus:ring-[#315C50]"
            />
          </div>
          <div>
            <label className="block text-xs font-semibold text-[#202B28] mb-1.5">Email</label>
            <input
              required
              type="email"
              value={form.email}
              onChange={(e) => setForm({ ...form, email: e.target.value })}
              className="w-full h-10 px-3 rounded-lg border border-[#E5E5DE] text-sm focus:outline-none focus:ring-2 focus:ring-[#315C50]"
            />
          </div>
          <div>
            <label className="block text-xs font-semibold text-[#202B28] mb-1.5">Temporary password</label>
            <input
              required
              type="password"
              minLength={8}
              value={form.password}
              onChange={(e) => setForm({ ...form, password: e.target.value })}
              className="w-full h-10 px-3 rounded-lg border border-[#E5E5DE] text-sm focus:outline-none focus:ring-2 focus:ring-[#315C50]"
            />
          </div>
          <div>
            <label className="block text-xs font-semibold text-[#202B28] mb-1.5">Role</label>
            <select
              value={form.role}
              onChange={(e) => setForm({ ...form, role: e.target.value as UserRole })}
              className="w-full h-10 px-3 rounded-lg border border-[#E5E5DE] text-sm bg-white focus:outline-none focus:ring-2 focus:ring-[#315C50]"
            >
              {ROLE_OPTIONS.map((r) => (
                <option key={r} value={r}>
                  {r.replace("_", " ")}
                </option>
              ))}
            </select>
          </div>
          {formError && (
            <p className="md:col-span-4 text-sm text-[#C34D4D]">{formError}</p>
          )}
          <div className="md:col-span-4">
            <button
              type="submit"
              disabled={submitting}
              className="h-10 px-4 rounded-lg bg-[#315C50] hover:bg-[#3c6e60] disabled:opacity-60 text-white text-sm font-semibold flex items-center gap-2"
            >
              {submitting && <Loader2 className="w-4 h-4 animate-spin" />}
              Create account
            </button>
          </div>
        </form>
      )}

      <div className="bg-white rounded-xl border border-[#E5E5DE] shadow-xs overflow-hidden">
        <div className="px-6 py-4 border-b border-[#E5E5DE] flex items-center gap-2">
          <UserCog className="w-4 h-4 text-[#173B35]" />
          <h2 className="text-sm font-semibold text-[#202B28]">All staff accounts</h2>
        </div>

        {error && <p className="px-6 py-4 text-sm text-[#C34D4D]">{error}</p>}

        {loading ? (
          <div className="px-6 py-8 text-center text-sm text-[#737C76]">Loading...</div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs font-semibold text-[#737C76] uppercase tracking-wider border-b border-[#E5E5DE]">
                <th className="px-6 py-3">Name</th>
                <th className="px-6 py-3">Email</th>
                <th className="px-6 py-3">Role</th>
                <th className="px-6 py-3">Status</th>
                <th className="px-6 py-3 text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {staff.map((member) => (
                <tr key={member.id} className="border-b border-[#F0F1EC] last:border-0">
                  <td className="px-6 py-3 font-medium text-[#202B28]">{member.full_name}</td>
                  <td className="px-6 py-3 text-[#737C76]">{member.email}</td>
                  <td className="px-6 py-3">
                    <span className="text-xs font-semibold px-2 py-1 rounded-md bg-[#F0F1EC] text-[#202B28]">
                      {member.role.replace("_", " ")}
                    </span>
                  </td>
                  <td className="px-6 py-3">
                    <span
                      className={`text-xs font-semibold px-2 py-1 rounded-md ${
                        member.is_active
                          ? "bg-[#E9F5EF] text-[#27845B]"
                          : "bg-[#FDF2F2] text-[#C34D4D]"
                      }`}
                    >
                      {member.is_active ? "Active" : "Deactivated"}
                    </span>
                  </td>
                  <td className="px-6 py-3 text-right">
                    <button
                      onClick={() => toggleActive(member)}
                      disabled={member.id === user.id}
                      className="text-xs font-semibold text-[#173B35] hover:underline disabled:text-[#C5C5BB] disabled:no-underline disabled:cursor-not-allowed"
                    >
                      {member.is_active ? "Deactivate" : "Activate"}
                    </button>
                  </td>
                </tr>
              ))}
              {staff.length === 0 && (
                <tr>
                  <td colSpan={5} className="px-6 py-8 text-center text-sm text-[#737C76]">
                    No staff accounts yet.
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
