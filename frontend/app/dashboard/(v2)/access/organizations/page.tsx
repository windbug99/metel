"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { usePathname, useRouter } from "next/navigation";

import { buildNextPath, dashboardApiGet, dashboardApiRequest } from "../../../../../lib/dashboard-v2-client";
import AlertBanner from "../../../../../components/dashboard-v2/alert-banner";

type PermissionSnapshot = {
  user_id: string;
  role: string;
};

type OrganizationItem = {
  id: number;
  name: string;
  role: "owner" | "admin" | "member";
  created_at?: string | null;
  updated_at?: string | null;
};

type MemberItem = {
  id?: number;
  organization_id: number | string;
  user_id: string;
  role: "owner" | "admin" | "member";
  created_at?: string | null;
};

type InviteItem = {
  id: number;
  organization_id: number | string;
  token: string;
  invited_email?: string | null;
  role: "owner" | "admin" | "member";
  invited_by?: string | null;
  expires_at?: string | null;
  accepted_by?: string | null;
  accepted_at?: string | null;
  revoked_at?: string | null;
  created_at?: string | null;
};

function formatDate(value?: string | null): string {
  if (!value) {
    return "-";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString();
}

export default function DashboardOrganizationsPage() {
  const pathname = usePathname();
  const router = useRouter();

  const [me, setMe] = useState<PermissionSnapshot | null>(null);
  const [organizations, setOrganizations] = useState<OrganizationItem[]>([]);
  const [selectedOrgId, setSelectedOrgId] = useState("");
  const [members, setMembers] = useState<MemberItem[]>([]);
  const [invites, setInvites] = useState<InviteItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [createOrgName, setCreateOrgName] = useState("");
  const [creatingOrg, setCreatingOrg] = useState(false);

  const [memberUserId, setMemberUserId] = useState("");
  const [memberRole, setMemberRole] = useState<"owner" | "admin" | "member">("member");
  const [savingMember, setSavingMember] = useState(false);

  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState<"owner" | "admin" | "member">("member");
  const [inviteHours, setInviteHours] = useState("72");
  const [creatingInvite, setCreatingInvite] = useState(false);

  const [acceptToken, setAcceptToken] = useState("");
  const [acceptingInvite, setAcceptingInvite] = useState(false);

  const selectedOrg = useMemo(
    () => organizations.find((item) => String(item.id) === selectedOrgId) ?? null,
    [organizations, selectedOrgId]
  );
  const ownerActionsEnabled = selectedOrg?.role === "owner";

  const handle401 = useCallback(() => {
    const next = encodeURIComponent(buildNextPath(pathname, window.location.search));
    router.replace(`/?next=${next}`);
  }, [pathname, router]);

  const loadOrganizations = useCallback(async () => {
    setLoading(true);
    setError(null);

    const meResult = await dashboardApiGet<PermissionSnapshot>("/api/me/permissions");
    if (meResult.status === 401) {
      handle401();
      setLoading(false);
      return;
    }
    if (!meResult.ok || !meResult.data) {
      setError(meResult.error ?? "Failed to load profile.");
      setLoading(false);
      return;
    }
    setMe(meResult.data);

    const orgResult = await dashboardApiGet<{ items?: OrganizationItem[] }>("/api/organizations");
    if (orgResult.status === 401) {
      handle401();
      setLoading(false);
      return;
    }
    if (orgResult.status === 403) {
      setError("Access denied while loading organizations.");
      setLoading(false);
      return;
    }
    if (!orgResult.ok || !orgResult.data) {
      setError(orgResult.error ?? "Failed to load organizations.");
      setLoading(false);
      return;
    }

    const nextItems = Array.isArray(orgResult.data.items) ? orgResult.data.items : [];
    setOrganizations(nextItems);
    setSelectedOrgId((prev) => {
      if (prev && nextItems.some((item) => String(item.id) === prev)) {
        return prev;
      }
      return nextItems.length > 0 ? String(nextItems[0].id) : "";
    });
    setLoading(false);
  }, [handle401]);

  const loadMembers = useCallback(async () => {
    if (!selectedOrgId) {
      setMembers([]);
      return;
    }
    setError(null);
    const result = await dashboardApiGet<{ items?: MemberItem[] }>(`/api/organizations/${selectedOrgId}/members`);
    if (result.status === 401) {
      handle401();
      return;
    }
    if (result.status === 403 || result.status === 404) {
      setError("Cannot load members for this organization.");
      return;
    }
    if (!result.ok || !result.data) {
      setError(result.error ?? "Failed to load members.");
      return;
    }
    setMembers(Array.isArray(result.data.items) ? result.data.items : []);
  }, [handle401, selectedOrgId]);

  const loadInvites = useCallback(async () => {
    if (!selectedOrgId) {
      setInvites([]);
      return;
    }
    setError(null);
    const result = await dashboardApiGet<{ items?: InviteItem[] }>(`/api/organizations/${selectedOrgId}/invites`);
    if (result.status === 401) {
      handle401();
      return;
    }
    if (result.status === 403 || result.status === 404) {
      setError("Cannot load invites for this organization.");
      return;
    }
    if (!result.ok || !result.data) {
      setError(result.error ?? "Failed to load invites.");
      return;
    }
    setInvites(Array.isArray(result.data.items) ? result.data.items : []);
  }, [handle401, selectedOrgId]);

  const createOrganization = useCallback(async () => {
    const name = createOrgName.trim();
    if (!name) {
      setError("Organization name is required.");
      return;
    }
    setCreatingOrg(true);
    setError(null);
    const result = await dashboardApiRequest<{ item?: OrganizationItem }>("/api/organizations", {
      method: "POST",
      body: { name },
    });
    if (result.status === 401) {
      handle401();
      setCreatingOrg(false);
      return;
    }
    if (result.status === 403) {
      setError("Access denied while creating organization.");
      setCreatingOrg(false);
      return;
    }
    if (!result.ok) {
      setError(result.error ?? "Failed to create organization.");
      setCreatingOrg(false);
      return;
    }
    setCreateOrgName("");
    await loadOrganizations();
    setCreatingOrg(false);
  }, [createOrgName, handle401, loadOrganizations]);

  const saveMember = useCallback(async () => {
    if (!selectedOrgId) {
      setError("Select an organization first.");
      return;
    }
    if (!memberUserId.trim()) {
      setError("User ID is required.");
      return;
    }
    setSavingMember(true);
    setError(null);
    const result = await dashboardApiRequest(`/api/organizations/${selectedOrgId}/members`, {
      method: "POST",
      body: {
        user_id: memberUserId.trim(),
        role: memberRole,
      },
    });
    if (result.status === 401) {
      handle401();
      setSavingMember(false);
      return;
    }
    if (result.status === 403 || result.status === 404) {
      setError("Owner role required for member updates.");
      setSavingMember(false);
      return;
    }
    if (!result.ok) {
      setError(result.error ?? "Failed to save member.");
      setSavingMember(false);
      return;
    }
    setMemberUserId("");
    await loadMembers();
    setSavingMember(false);
  }, [handle401, loadMembers, memberRole, memberUserId, selectedOrgId]);

  const deleteMember = useCallback(
    async (targetUserId: string) => {
      if (!selectedOrgId) {
        return;
      }
      setError(null);
      const result = await dashboardApiRequest(`/api/organizations/${selectedOrgId}/members/${targetUserId}`, {
        method: "DELETE",
      });
      if (result.status === 401) {
        handle401();
        return;
      }
      if (result.status === 403 || result.status === 404) {
        setError("Owner role required for member deletion.");
        return;
      }
      if (!result.ok) {
        setError(result.error ?? "Failed to delete member.");
        return;
      }
      await loadMembers();
    },
    [handle401, loadMembers, selectedOrgId]
  );

  const createInvite = useCallback(async () => {
    if (!selectedOrgId) {
      setError("Select an organization first.");
      return;
    }
    setCreatingInvite(true);
    setError(null);
    const hours = Number(inviteHours);
    const result = await dashboardApiRequest(`/api/organizations/${selectedOrgId}/invites`, {
      method: "POST",
      body: {
        role: inviteRole,
        invited_email: inviteEmail.trim() || null,
        expires_in_hours: Number.isFinite(hours) ? hours : 72,
      },
    });
    if (result.status === 401) {
      handle401();
      setCreatingInvite(false);
      return;
    }
    if (result.status === 403 || result.status === 404) {
      setError("Owner role required for invite creation.");
      setCreatingInvite(false);
      return;
    }
    if (!result.ok) {
      setError(result.error ?? "Failed to create invite.");
      setCreatingInvite(false);
      return;
    }
    setInviteEmail("");
    await loadInvites();
    setCreatingInvite(false);
  }, [handle401, inviteEmail, inviteHours, inviteRole, loadInvites, selectedOrgId]);

  const invokeInviteAction = useCallback(
    async (inviteId: number, action: "revoke" | "reissue") => {
      if (!selectedOrgId) {
        return;
      }
      setError(null);
      const result = await dashboardApiRequest(`/api/organizations/${selectedOrgId}/invites/${inviteId}/${action}`, {
        method: "POST",
      });
      if (result.status === 401) {
        handle401();
        return;
      }
      if (result.status === 403 || result.status === 404) {
        setError("Owner role required for invite management.");
        return;
      }
      if (!result.ok) {
        setError(result.error ?? `Failed to ${action} invite.`);
        return;
      }
      await loadInvites();
    },
    [handle401, loadInvites, selectedOrgId]
  );

  const acceptInvite = useCallback(async () => {
    if (!acceptToken.trim()) {
      setError("Invite token is required.");
      return;
    }
    setAcceptingInvite(true);
    setError(null);
    const result = await dashboardApiRequest("/api/organizations/invites/accept", {
      method: "POST",
      body: { token: acceptToken.trim() },
    });
    if (result.status === 401) {
      handle401();
      setAcceptingInvite(false);
      return;
    }
    if (result.status === 403 || result.status === 404 || result.status === 409) {
      setError("Invite acceptance failed. Check token, role, and invite status.");
      setAcceptingInvite(false);
      return;
    }
    if (!result.ok) {
      setError(result.error ?? "Failed to accept invite.");
      setAcceptingInvite(false);
      return;
    }
    setAcceptToken("");
    await loadOrganizations();
    setAcceptingInvite(false);
  }, [acceptToken, handle401, loadOrganizations]);

  useEffect(() => {
    void loadOrganizations();
  }, [loadOrganizations]);

  useEffect(() => {
    if (!selectedOrgId) {
      setMembers([]);
      setInvites([]);
      return;
    }
    void loadMembers();
    void loadInvites();
  }, [loadInvites, loadMembers, selectedOrgId]);

  useEffect(() => {
    const handler = (event: Event) => {
      const custom = event as CustomEvent<{ path?: string }>;
      if (custom.detail?.path === pathname) {
        void loadOrganizations();
      }
    };
    window.addEventListener("dashboard:v2:refresh", handler as EventListener);
    return () => {
      window.removeEventListener("dashboard:v2:refresh", handler as EventListener);
    };
  }, [loadOrganizations, pathname]);

  return (
    <section className="space-y-4">
      <h1 className="text-2xl font-semibold">Organizations</h1>
      <p className="text-sm text-[var(--text-secondary)]">
        Organization creation, member role updates, and invite actions are available in route-based V2.
      </p>

      {error ? <AlertBanner message={error} tone="danger" /> : null}
      {loading ? <p className="text-sm text-[var(--muted)]">Loading organizations...</p> : null}

      <div className="ds-card p-4">
        <p className="mb-2 text-sm font-medium">Create organization</p>
        <div className="flex flex-wrap items-center gap-2">
          <input
            value={createOrgName}
            onChange={(event) => setCreateOrgName(event.target.value)}
            placeholder="Organization name"
            className="ds-input h-11 rounded-md px-3 text-sm md:h-9"
          />
          <button
            type="button"
            onClick={() => void createOrganization()}
            disabled={creatingOrg}
            className="ds-btn h-11 rounded-md px-3 text-sm disabled:cursor-not-allowed disabled:opacity-60 md:h-9"
          >
            {creatingOrg ? "Creating..." : "Create Organization"}
          </button>
        </div>
      </div>

      <div className="ds-card p-4">
        <p className="mb-2 text-sm font-medium">Accept invite token</p>
        <div className="flex flex-wrap items-center gap-2">
          <input
            value={acceptToken}
            onChange={(event) => setAcceptToken(event.target.value)}
            placeholder="Invite token"
            className="ds-input h-11 min-w-[280px] rounded-md px-3 text-sm md:h-9"
          />
          <button
            type="button"
            onClick={() => void acceptInvite()}
            disabled={acceptingInvite}
            className="ds-btn h-11 rounded-md px-3 text-sm disabled:cursor-not-allowed disabled:opacity-60 md:h-9"
          >
            {acceptingInvite ? "Accepting..." : "Accept Invite"}
          </button>
        </div>
      </div>

      <div className="ds-card p-4">
        <div className="flex flex-wrap items-center gap-2">
          <label className="text-sm text-[var(--muted)]">Organization</label>
          <select
            value={selectedOrgId}
            onChange={(event) => setSelectedOrgId(event.target.value)}
            className="ds-input h-11 rounded-md px-3 text-sm md:h-9"
          >
            {organizations.length === 0 ? <option value="">No organizations</option> : null}
            {organizations.map((item) => (
              <option key={`org-${item.id}`} value={String(item.id)}>
                Org #{item.id} - {item.name} ({item.role})
              </option>
            ))}
          </select>
          <button type="button" onClick={() => void loadMembers()} className="ds-btn h-11 rounded-md px-3 text-sm md:h-9">
            Load Members
          </button>
          <button type="button" onClick={() => void loadInvites()} className="ds-btn h-11 rounded-md px-3 text-sm md:h-9">
            Load Invites
          </button>
        </div>
        <p className="mt-2 text-xs text-[var(--muted)]">
          signed-in user: {me?.user_id ?? "-"} / selected org role: {selectedOrg?.role ?? "-"}
        </p>
      </div>

      <div className="ds-card p-4">
        <p className="mb-2 text-sm font-medium">Add / update member</p>
        <div className="flex flex-wrap items-center gap-2">
          <input
            value={memberUserId}
            onChange={(event) => setMemberUserId(event.target.value)}
            placeholder="User ID"
            className="ds-input h-11 min-w-[320px] rounded-md px-3 text-sm md:h-9"
          />
          <select
            value={memberRole}
            onChange={(event) => setMemberRole(event.target.value as "owner" | "admin" | "member")}
            className="ds-input h-11 rounded-md px-3 text-sm md:h-9"
          >
            <option value="owner">owner</option>
            <option value="admin">admin</option>
            <option value="member">member</option>
          </select>
          <button
            type="button"
            onClick={() => void saveMember()}
            disabled={!ownerActionsEnabled || savingMember}
            className="ds-btn h-11 rounded-md px-3 text-sm disabled:cursor-not-allowed disabled:opacity-60 md:h-9"
            title={ownerActionsEnabled ? "" : "Owner role required"}
          >
            {savingMember ? "Saving..." : "Add / Update Member"}
          </button>
        </div>
        {!ownerActionsEnabled ? <p className="mt-2 text-xs text-[var(--muted)]">Owner role required.</p> : null}
      </div>

      <div className="ds-card overflow-x-auto">
        <table className="min-w-[640px] text-sm">
          <thead className="bg-[var(--surface-subtle)] text-left text-xs text-[var(--muted)]">
            <tr>
              <th className="px-4 py-3">User ID</th>
              <th className="px-4 py-3">Role</th>
              <th className="px-4 py-3">Created At</th>
              <th className="px-4 py-3">Action</th>
            </tr>
          </thead>
          <tbody>
            {members.map((item) => (
              <tr key={`member-${item.user_id}`} className="border-t border-[var(--border)]">
                <td className="px-4 py-3 font-mono text-xs">{item.user_id}</td>
                <td className="px-4 py-3">{item.role}</td>
                <td className="px-4 py-3">{formatDate(item.created_at)}</td>
                <td className="px-4 py-3">
                  <button
                    type="button"
                    disabled={!ownerActionsEnabled || item.user_id === me?.user_id}
                    onClick={() => void deleteMember(item.user_id)}
                    className="ds-btn h-11 rounded-md px-3 text-xs disabled:cursor-not-allowed disabled:opacity-60 md:h-9"
                    title={item.user_id === me?.user_id ? "Cannot remove signed-in owner" : ownerActionsEnabled ? "" : "Owner role required"}
                  >
                    Delete
                  </button>
                </td>
              </tr>
            ))}
            {members.length === 0 ? (
              <tr>
                <td className="px-4 py-4 text-[var(--muted)]" colSpan={4}>
                  No members loaded.
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>

      <div className="ds-card p-4">
        <p className="mb-2 text-sm font-medium">Create invite</p>
        <div className="flex flex-wrap items-center gap-2">
          <input
            value={inviteEmail}
            onChange={(event) => setInviteEmail(event.target.value)}
            placeholder="Invited email (optional)"
            className="ds-input h-11 min-w-[280px] rounded-md px-3 text-sm md:h-9"
          />
          <select
            value={inviteRole}
            onChange={(event) => setInviteRole(event.target.value as "owner" | "admin" | "member")}
            className="ds-input h-11 rounded-md px-3 text-sm md:h-9"
          >
            <option value="owner">owner</option>
            <option value="admin">admin</option>
            <option value="member">member</option>
          </select>
          <input
            value={inviteHours}
            onChange={(event) => setInviteHours(event.target.value)}
            placeholder="Hours"
            className="ds-input h-11 w-24 rounded-md px-3 text-sm md:h-9"
          />
          <button
            type="button"
            onClick={() => void createInvite()}
            disabled={!ownerActionsEnabled || creatingInvite}
            className="ds-btn h-11 rounded-md px-3 text-sm disabled:cursor-not-allowed disabled:opacity-60 md:h-9"
            title={ownerActionsEnabled ? "" : "Owner role required"}
          >
            {creatingInvite ? "Creating..." : "Create Invite"}
          </button>
        </div>
      </div>

      <div className="ds-card overflow-x-auto">
        <table className="min-w-[880px] text-sm">
          <thead className="bg-[var(--surface-subtle)] text-left text-xs text-[var(--muted)]">
            <tr>
              <th className="px-4 py-3">ID</th>
              <th className="px-4 py-3">Role</th>
              <th className="px-4 py-3">Invited Email</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3">Expires</th>
              <th className="px-4 py-3">Token</th>
              <th className="px-4 py-3">Action</th>
            </tr>
          </thead>
          <tbody>
            {invites.map((item) => {
              const status = item.revoked_at ? "revoked" : item.accepted_at ? "accepted" : "pending";
              return (
                <tr key={`invite-${item.id}`} className="border-t border-[var(--border)]">
                  <td className="px-4 py-3">#{item.id}</td>
                  <td className="px-4 py-3">{item.role}</td>
                  <td className="px-4 py-3">{item.invited_email || "-"}</td>
                  <td className="px-4 py-3">{status}</td>
                  <td className="px-4 py-3">{formatDate(item.expires_at)}</td>
                  <td className="px-4 py-3 font-mono text-xs">{item.token}</td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <button
                        type="button"
                        disabled={!ownerActionsEnabled || status !== "pending"}
                        onClick={() => void invokeInviteAction(item.id, "revoke")}
                        className="ds-btn h-11 rounded-md px-3 text-xs disabled:cursor-not-allowed disabled:opacity-60 md:h-9"
                        title={ownerActionsEnabled ? "" : "Owner role required"}
                      >
                        Revoke
                      </button>
                      <button
                        type="button"
                        disabled={!ownerActionsEnabled || status !== "pending"}
                        onClick={() => void invokeInviteAction(item.id, "reissue")}
                        className="ds-btn h-11 rounded-md px-3 text-xs disabled:cursor-not-allowed disabled:opacity-60 md:h-9"
                        title={ownerActionsEnabled ? "" : "Owner role required"}
                      >
                        Reissue
                      </button>
                    </div>
                  </td>
                </tr>
              );
            })}
            {invites.length === 0 ? (
              <tr>
                <td className="px-4 py-4 text-[var(--muted)]" colSpan={7}>
                  No invites loaded.
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
    </section>
  );
}
