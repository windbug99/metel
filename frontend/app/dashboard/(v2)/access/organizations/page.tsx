"use client";

import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Select } from "@/components/ui/select";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { useCallback, useEffect, useMemo, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Loader2 } from "lucide-react";

import { buildNextPath, dashboardApiGet, dashboardApiRequest } from "../../../../../lib/dashboard-v2-client";
import AlertBanner from "../../../../../components/dashboard-v2/alert-banner";
import PageTitleWithTooltip from "@/components/dashboard-v2/page-title-with-tooltip";

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

type OrganizationRoleRequestItem = {
  id: number;
  organization_id: number;
  target_user_id: string;
  requested_role: "owner" | "admin" | "member";
  reason?: string | null;
  status: string;
  requested_by: string;
  reviewed_by?: string | null;
  reviewed_at?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
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
  const searchParams = useSearchParams();

  const [me, setMe] = useState<PermissionSnapshot | null>(null);
  const [organizations, setOrganizations] = useState<OrganizationItem[]>([]);
  const [selectedOrgId, setSelectedOrgId] = useState("");
  const [members, setMembers] = useState<MemberItem[]>([]);
  const [invites, setInvites] = useState<InviteItem[]>([]);
  const [roleRequests, setRoleRequests] = useState<OrganizationRoleRequestItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [createOrgName, setCreateOrgName] = useState("");
  const [creatingOrg, setCreatingOrg] = useState(false);
  const [createOrgDialogOpen, setCreateOrgDialogOpen] = useState(false);

  const [memberUserId, setMemberUserId] = useState("");
  const [memberRole, setMemberRole] = useState<"owner" | "admin" | "member">("member");
  const [savingMember, setSavingMember] = useState(false);

  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState<"owner" | "admin" | "member">("member");
  const [inviteHours, setInviteHours] = useState("72");
  const [creatingInvite, setCreatingInvite] = useState(false);

  const [roleRequestTargetUserId, setRoleRequestTargetUserId] = useState("");
  const [roleRequestRequestedRole, setRoleRequestRequestedRole] = useState<"owner" | "admin" | "member">("member");
  const [roleRequestReason, setRoleRequestReason] = useState("");
  const [loadingRoleRequests, setLoadingRoleRequests] = useState(false);
  const [creatingRoleRequest, setCreatingRoleRequest] = useState(false);
  const [reviewingRoleRequestAction, setReviewingRoleRequestAction] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<"users" | "invites" | "requests">("users");

  const selectedOrg = useMemo(
    () => organizations.find((item) => String(item.id) === selectedOrgId) ?? null,
    [organizations, selectedOrgId]
  );
  const orgFromQuery = searchParams.get("org");
  const selectedOrgRole = selectedOrg?.role ?? null;
  const ownerActionsEnabled = selectedOrgRole === "owner";
  const adminOrOwnerActionsEnabled = selectedOrgRole === "owner" || selectedOrgRole === "admin";
  const roleRequestCreateEnabled = Boolean(selectedOrgRole);

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
      if (orgFromQuery && nextItems.some((item) => String(item.id) === orgFromQuery)) {
        return orgFromQuery;
      }
      if (prev && nextItems.some((item) => String(item.id) === prev)) {
        return prev;
      }
      return nextItems.length > 0 ? String(nextItems[0].id) : "";
    });
    setLoading(false);
  }, [handle401, orgFromQuery]);

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
    setCreateOrgDialogOpen(false);
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
      setError("Member update is not allowed for current role/target.");
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
        setError("Member deletion is not allowed for current role/target.");
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
      setError("Invite creation is not allowed for current role.");
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
        setError("Invite action is not allowed for current role.");
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

  const loadRoleRequests = useCallback(async () => {
    if (!selectedOrgId) {
      setRoleRequests([]);
      return;
    }
    setLoadingRoleRequests(true);
    setError(null);
    const result = await dashboardApiGet<{ items?: OrganizationRoleRequestItem[] }>(
      `/api/organizations/${selectedOrgId}/role-requests`
    );
    if (result.status === 401) {
      handle401();
      setLoadingRoleRequests(false);
      return;
    }
    if (result.status === 403 || result.status === 404) {
      setError("Cannot load role requests for this organization.");
      setLoadingRoleRequests(false);
      return;
    }
    if (!result.ok || !result.data) {
      setError(result.error ?? "Failed to load role requests.");
      setLoadingRoleRequests(false);
      return;
    }
    setRoleRequests(Array.isArray(result.data.items) ? result.data.items : []);
    setLoadingRoleRequests(false);
  }, [handle401, selectedOrgId]);

  const createRoleRequest = useCallback(async () => {
    if (!selectedOrgId) {
      setError("Select an organization first.");
      return;
    }
    const targetUserId =
      selectedOrgRole === "member" ? (me?.user_id ?? "").trim() : roleRequestTargetUserId.trim();
    if (!targetUserId) {
      setError("Role request target user_id is required.");
      return;
    }
    setCreatingRoleRequest(true);
    setError(null);
    const result = await dashboardApiRequest(`/api/organizations/${selectedOrgId}/role-requests`, {
      method: "POST",
      body: {
        target_user_id: targetUserId,
        requested_role: roleRequestRequestedRole,
        reason: roleRequestReason.trim() || null,
      },
    });
    if (result.status === 401) {
      handle401();
      setCreatingRoleRequest(false);
      return;
    }
    if (result.status === 403 || result.status === 404) {
      setError("Role request creation is not allowed for this target/role.");
      setCreatingRoleRequest(false);
      return;
    }
    if (!result.ok) {
      setError(result.error ?? "Failed to create role request.");
      setCreatingRoleRequest(false);
      return;
    }
    setRoleRequestTargetUserId("");
    setRoleRequestRequestedRole("member");
    setRoleRequestReason("");
    await loadRoleRequests();
    setCreatingRoleRequest(false);
  }, [handle401, loadRoleRequests, me?.user_id, roleRequestReason, roleRequestRequestedRole, roleRequestTargetUserId, selectedOrgId, selectedOrgRole]);

  const reviewRoleRequest = useCallback(
    async (requestId: number, decision: "approve" | "reject") => {
      if (!selectedOrgId) {
        return;
      }
      const reason =
        decision === "reject"
          ? window.prompt("Enter rejection reason (optional). This will be visible to the requester.")?.trim() || null
          : null;
      const reviewKey = `${requestId}:${decision}`;
      setReviewingRoleRequestAction(reviewKey);
      setError(null);
      const result = await dashboardApiRequest(`/api/organizations/${selectedOrgId}/role-requests/${requestId}/review`, {
        method: "POST",
        body: { decision, reason },
      });
      if (result.status === 401) {
        handle401();
        setReviewingRoleRequestAction(null);
        return;
      }
      if (result.status === 403 || result.status === 404) {
        setError("Owner role required for role request review.");
        setReviewingRoleRequestAction(null);
        return;
      }
      if (!result.ok) {
        setError(result.error ?? "Failed to review role request.");
        setReviewingRoleRequestAction(null);
        return;
      }
      await Promise.all([loadRoleRequests(), loadMembers()]);
      setReviewingRoleRequestAction(null);
    },
    [handle401, loadMembers, loadRoleRequests, selectedOrgId]
  );

  useEffect(() => {
    void loadOrganizations();
  }, [loadOrganizations]);

  useEffect(() => {
    if (!selectedOrgId) {
      setMembers([]);
      setInvites([]);
      setRoleRequests([]);
      return;
    }
    void loadMembers();
    void loadInvites();
    void loadRoleRequests();
  }, [loadInvites, loadMembers, loadRoleRequests, selectedOrgId]);

  useEffect(() => {
    if (!selectedOrgId) {
      return;
    }
    const params = new URLSearchParams(searchParams.toString());
    if (params.get("org") === selectedOrgId && params.get("scope") === "org") {
      return;
    }
    params.set("scope", "org");
    params.set("org", selectedOrgId);
    params.delete("team");
    const encoded = params.toString();
    router.replace(encoded ? `${pathname}?${encoded}` : pathname);
  }, [pathname, router, searchParams, selectedOrgId]);

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

  useEffect(() => {
    const openFromSidebar = () => setCreateOrgDialogOpen(true);
    const storageKey = "dashboard:v2:open-create-organization";
    if (window.sessionStorage.getItem(storageKey) === "1") {
      setCreateOrgDialogOpen(true);
      window.sessionStorage.removeItem(storageKey);
    }
    window.addEventListener("dashboard:v2:open-create-organization", openFromSidebar);
    return () => {
      window.removeEventListener("dashboard:v2:open-create-organization", openFromSidebar);
    };
  }, []);

  useEffect(() => {
    if (selectedOrgRole !== "member") {
      return;
    }
    if (!me?.user_id) {
      return;
    }
    setRoleRequestTargetUserId((prev) => (prev.trim() ? prev : me.user_id));
    if (roleRequestRequestedRole === "owner") {
      setRoleRequestRequestedRole("admin");
    }
  }, [me?.user_id, roleRequestRequestedRole, selectedOrgRole]);

  if (loading) {
    return (
      <section className="space-y-4">
        <PageTitleWithTooltip title="Organizations" tooltip="Manage organizations, members, invites, and role requests." />
        <p className="text-sm text-muted-foreground">
          Owner/Admin can manage members and invites. Role requests can be created by all roles, and only owner can approve.
        </p>
        <div className="ds-card flex min-h-[220px] items-center justify-center p-4">
          <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
        </div>
      </section>
    );
  }

  return (
    <section className="space-y-4">
      <PageTitleWithTooltip title="Organizations" tooltip="Manage organizations, members, invites, and role requests." />
      <p className="text-sm text-muted-foreground">
        Owner/Admin can manage members and invites. Role requests can be created by all roles, and only owner can approve.
      </p>

      {error ? <AlertBanner message={error} tone="danger" /> : null}

      <Dialog open={createOrgDialogOpen} onOpenChange={setCreateOrgDialogOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Create organization</DialogTitle>
            <DialogDescription>Create a new organization and refresh current organization list.</DialogDescription>
          </DialogHeader>
          <form
            className="space-y-3"
            onSubmit={(event) => {
              event.preventDefault();
              void createOrganization();
            }}
          >
            <Input
              value={createOrgName}
              onChange={(event) => setCreateOrgName(event.target.value)}
              placeholder="Organization name"
              className="h-10"
            />
            <DialogFooter>
              <Button
                type="button"
                variant="outline"
                className="border-border bg-card text-foreground hover:bg-accent hover:text-accent-foreground"
                onClick={() => setCreateOrgDialogOpen(false)}
              >
                Cancel
              </Button>
              <Button
                type="submit"
                disabled={creatingOrg}
                className="bg-sidebar-primary text-sidebar-primary-foreground hover:bg-sidebar-primary/90"
              >
                {creatingOrg ? "Creating..." : "Create Organization"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <div className="ds-card p-4">
        <p className="text-xs text-muted-foreground">
          signed-in user: {me?.user_id ?? "-"} / selected org role: {selectedOrg?.role ?? "-"}
        </p>
      </div>

      <Tabs
        value={activeTab}
        onValueChange={(value) => setActiveTab(value as "users" | "invites" | "requests")}
        className="space-y-4"
      >
        <TabsList className="ds-card h-auto w-full justify-start gap-2 p-2">
          <TabsTrigger value="users" className="h-9 rounded-md px-3 text-sm">
            Users
          </TabsTrigger>
          <TabsTrigger value="invites" className="h-9 rounded-md px-3 text-sm">
            Invites
          </TabsTrigger>
          <TabsTrigger value="requests" className="h-9 rounded-md px-3 text-sm">
            Requests
          </TabsTrigger>
        </TabsList>

        <TabsContent value="users" className="space-y-4">
          <div className="ds-card p-4">
            <p className="mb-2 text-sm font-semibold">Add / update member</p>
            <div className="flex items-center gap-2">
              <Input
                value={memberUserId}
                onChange={(event) => setMemberUserId(event.target.value)}
                placeholder="User ID"
                className="ds-input h-11 min-w-[320px] flex-1 rounded-md px-3 text-sm md:h-9"
              />
              <Select
                value={memberRole}
                onChange={(event) => setMemberRole(event.target.value as "owner" | "admin" | "member")}
                className="ds-input h-11 w-[160px] shrink-0 rounded-md px-3 text-sm md:h-9"
              >
                {selectedOrgRole === "owner" ? <option value="owner">owner</option> : null}
                {selectedOrgRole === "owner" ? <option value="admin">admin</option> : null}
                <option value="member">member</option>
              </Select>
              <Button
                type="button"
                onClick={() => void saveMember()}
                disabled={!adminOrOwnerActionsEnabled || savingMember}
                className="ds-btn h-11 shrink-0 rounded-md px-3 text-sm disabled:cursor-not-allowed disabled:opacity-60 md:h-9"
                title={adminOrOwnerActionsEnabled ? "" : "Admin or owner role required"}
              >
                {savingMember ? "Saving..." : "Add / Update Member"}
              </Button>
            </div>
            {!adminOrOwnerActionsEnabled ? <p className="mt-2 text-xs text-muted-foreground">Admin or owner role required.</p> : null}
            {selectedOrgRole === "admin" ? (
              <p className="mt-2 text-xs text-muted-foreground">Admin can assign member role only.</p>
            ) : null}
          </div>

          <div className="ds-card overflow-x-auto">
            <Table className="min-w-[640px] text-sm">
              <TableHeader className="bg-muted/60 text-left text-xs text-muted-foreground">
                <TableRow>
                  <TableHead className="px-4 py-3">User ID</TableHead>
                  <TableHead className="px-4 py-3">Role</TableHead>
                  <TableHead className="px-4 py-3">Created At</TableHead>
                  <TableHead className="px-4 py-3">Action</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {members.map((item) => (
                  <TableRow key={`member-${item.user_id}`} className="border-t border-border">
                    <TableCell className="px-4 py-3 font-mono text-xs">{item.user_id}</TableCell>
                    <TableCell className="px-4 py-3">{item.role}</TableCell>
                    <TableCell className="px-4 py-3">{formatDate(item.created_at)}</TableCell>
                    <TableCell className="px-4 py-3">
                      <Button
                        type="button"
                        disabled={
                          !adminOrOwnerActionsEnabled ||
                          item.user_id === me?.user_id ||
                          (selectedOrgRole === "admin" && item.role !== "member")
                        }
                        onClick={() => void deleteMember(item.user_id)}
                        className="ds-btn h-11 rounded-md px-3 text-xs disabled:cursor-not-allowed disabled:opacity-60 md:h-9"
                        title={
                          item.user_id === me?.user_id
                            ? "Cannot remove signed-in user"
                            : selectedOrgRole === "admin" && item.role !== "member"
                            ? "Admin can remove member role only"
                            : adminOrOwnerActionsEnabled
                            ? ""
                            : "Admin or owner role required"
                        }
                      >
                        Delete
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
                {members.length === 0 ? (
                  <TableRow>
                    <TableCell className="px-4 py-4 text-muted-foreground" colSpan={4}>
                      No members loaded.
                    </TableCell>
                  </TableRow>
                ) : null}
              </TableBody>
            </Table>
          </div>
        </TabsContent>

        <TabsContent value="invites" className="space-y-4">
          <div className="ds-card p-4">
            <p className="mb-2 text-sm font-semibold">Create invite</p>
            <div className="flex items-center gap-2">
              <Input
                value={inviteEmail}
                onChange={(event) => setInviteEmail(event.target.value)}
                placeholder="Invited email (optional)"
                className="ds-input h-11 min-w-[280px] flex-1 rounded-md px-3 text-sm md:h-9"
              />
              <Select
                value={inviteRole}
                onChange={(event) => setInviteRole(event.target.value as "owner" | "admin" | "member")}
                className="ds-input h-11 w-[160px] shrink-0 rounded-md px-3 text-sm md:h-9"
              >
                {selectedOrgRole === "owner" ? <option value="owner">owner</option> : null}
                {selectedOrgRole === "owner" ? <option value="admin">admin</option> : null}
                <option value="member">member</option>
              </Select>
              <Input
                value={inviteHours}
                onChange={(event) => setInviteHours(event.target.value)}
                placeholder="Hours"
                className="ds-input h-11 w-24 shrink-0 rounded-md px-3 text-sm md:h-9"
              />
              <Button
                type="button"
                onClick={() => void createInvite()}
                disabled={!adminOrOwnerActionsEnabled || creatingInvite}
                className="ds-btn h-11 shrink-0 rounded-md px-3 text-sm disabled:cursor-not-allowed disabled:opacity-60 md:h-9"
                title={adminOrOwnerActionsEnabled ? "" : "Admin or owner role required"}
              >
                {creatingInvite ? "Creating..." : "Create Invite"}
              </Button>
            </div>
            {selectedOrgRole === "admin" ? (
              <p className="mt-2 text-xs text-muted-foreground">Admin can invite member role only.</p>
            ) : null}
          </div>

          <div className="ds-card overflow-x-auto">
            <Table className="min-w-[880px] text-sm">
              <TableHeader className="bg-muted/60 text-left text-xs text-muted-foreground">
                <TableRow>
                  <TableHead className="px-4 py-3">ID</TableHead>
                  <TableHead className="px-4 py-3">Role</TableHead>
                  <TableHead className="px-4 py-3">Invited Email</TableHead>
                  <TableHead className="px-4 py-3">Status</TableHead>
                  <TableHead className="px-4 py-3">Expires</TableHead>
                  <TableHead className="px-4 py-3">Token</TableHead>
                  <TableHead className="px-4 py-3">Action</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {invites.map((item) => {
                  const status = item.revoked_at ? "revoked" : item.accepted_at ? "accepted" : "pending";
                  return (
                    <TableRow key={`invite-${item.id}`} className="border-t border-border">
                      <TableCell className="px-4 py-3">#{item.id}</TableCell>
                      <TableCell className="px-4 py-3">{item.role}</TableCell>
                      <TableCell className="px-4 py-3">{item.invited_email || "-"}</TableCell>
                      <TableCell className="px-4 py-3">{status}</TableCell>
                      <TableCell className="px-4 py-3">{formatDate(item.expires_at)}</TableCell>
                      <TableCell className="px-4 py-3 font-mono text-xs">{item.token}</TableCell>
                      <TableCell className="px-4 py-3">
                        <div className="flex items-center gap-2">
                          <Button
                            type="button"
                            disabled={!adminOrOwnerActionsEnabled || status !== "pending"}
                            onClick={() => void invokeInviteAction(item.id, "revoke")}
                            className="ds-btn h-11 rounded-md px-3 text-xs disabled:cursor-not-allowed disabled:opacity-60 md:h-9"
                            title={adminOrOwnerActionsEnabled ? "" : "Admin or owner role required"}
                          >
                            Revoke
                          </Button>
                          <Button
                            type="button"
                            disabled={!adminOrOwnerActionsEnabled || status !== "pending"}
                            onClick={() => void invokeInviteAction(item.id, "reissue")}
                            className="ds-btn h-11 rounded-md px-3 text-xs disabled:cursor-not-allowed disabled:opacity-60 md:h-9"
                            title={adminOrOwnerActionsEnabled ? "" : "Admin or owner role required"}
                          >
                            Reissue
                          </Button>
                        </div>
                      </TableCell>
                    </TableRow>
                  );
                })}
                {invites.length === 0 ? (
                  <TableRow>
                    <TableCell className="px-4 py-4 text-muted-foreground" colSpan={7}>
                      No invites loaded.
                    </TableCell>
                  </TableRow>
                ) : null}
              </TableBody>
            </Table>
          </div>
        </TabsContent>

        <TabsContent value="requests" className="space-y-4">
          <div className="ds-card p-4">
            <p className="mb-2 text-sm font-semibold">Role change requests</p>
            <div className="flex items-center gap-2">
              <Input
                value={selectedOrgRole === "member" ? (me?.user_id ?? "") : roleRequestTargetUserId}
                onChange={(event) => setRoleRequestTargetUserId(event.target.value)}
                placeholder={selectedOrgRole === "member" ? "self user_id" : "target user_id"}
                className="ds-input h-11 min-w-[220px] flex-1 rounded-md px-3 text-sm md:h-9"
                disabled={!roleRequestCreateEnabled || selectedOrgRole === "member"}
              />
              <Select
                value={roleRequestRequestedRole}
                onChange={(event) => setRoleRequestRequestedRole(event.target.value as "owner" | "admin" | "member")}
                className="ds-input h-11 w-[160px] shrink-0 rounded-md px-3 text-sm md:h-9"
                disabled={!roleRequestCreateEnabled}
              >
                <option value="member">member</option>
                <option value="admin">admin</option>
                {selectedOrgRole === "owner" ? <option value="owner">owner</option> : null}
              </Select>
              <Input
                value={roleRequestReason}
                onChange={(event) => setRoleRequestReason(event.target.value)}
                placeholder="reason (optional)"
                className="ds-input h-11 min-w-[180px] flex-1 rounded-md px-3 text-sm md:h-9"
                disabled={!roleRequestCreateEnabled}
              />
              <Button
                type="button"
                onClick={() => void createRoleRequest()}
                disabled={!roleRequestCreateEnabled || creatingRoleRequest}
                className="ds-btn h-11 shrink-0 rounded-md px-3 text-sm disabled:cursor-not-allowed disabled:opacity-60 md:h-9"
                title={roleRequestCreateEnabled ? "" : "Select organization first"}
              >
                {creatingRoleRequest ? "Creating..." : "Create Request"}
              </Button>
            </div>
            {selectedOrgRole === "member" ? (
              <p className="mt-2 text-xs text-muted-foreground">Member can request role change for self only.</p>
            ) : null}
            {selectedOrgRole === "admin" ? (
              <p className="mt-2 text-xs text-muted-foreground">Admin cannot request owner role.</p>
            ) : null}
          </div>

          <div className="ds-card overflow-x-auto">
            <Table className="min-w-[880px] text-sm">
              <TableHeader className="bg-muted/60 text-left text-xs text-muted-foreground">
                <TableRow>
                  <TableHead className="px-4 py-3">ID</TableHead>
                  <TableHead className="px-4 py-3">Target</TableHead>
                  <TableHead className="px-4 py-3">Requested Role</TableHead>
                  <TableHead className="px-4 py-3">Status</TableHead>
                  <TableHead className="px-4 py-3">Requested By</TableHead>
                  <TableHead className="px-4 py-3">Created At</TableHead>
                  <TableHead className="px-4 py-3">Action</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {roleRequests.map((item) => (
                  <TableRow key={`role-request-${item.id}`} className="border-t border-border">
                    <TableCell className="px-4 py-3">#{item.id}</TableCell>
                    <TableCell className="px-4 py-3 font-mono text-xs">{item.target_user_id}</TableCell>
                    <TableCell className="px-4 py-3">{item.requested_role}</TableCell>
                    <TableCell className="px-4 py-3">{item.status}</TableCell>
                    <TableCell className="px-4 py-3 font-mono text-xs">{item.requested_by}</TableCell>
                    <TableCell className="px-4 py-3">{formatDate(item.created_at)}</TableCell>
                    <TableCell className="px-4 py-3">
                      {item.status === "pending" && item.requested_by !== me?.user_id && ownerActionsEnabled ? (
                        <div className="flex items-center gap-2">
                          <Button
                            type="button"
                            onClick={() => void reviewRoleRequest(item.id, "approve")}
                            disabled={reviewingRoleRequestAction === `${item.id}:approve`}
                            className="h-11 rounded-md border border-chart-2/40 px-3 text-xs font-medium text-chart-2 disabled:opacity-60 md:h-9"
                          >
                            Approve
                          </Button>
                          <Button
                            type="button"
                            onClick={() => void reviewRoleRequest(item.id, "reject")}
                            disabled={reviewingRoleRequestAction === `${item.id}:reject`}
                            className="h-11 rounded-md border border-destructive/40 px-3 text-xs font-medium text-destructive disabled:opacity-60 md:h-9"
                          >
                            Reject
                          </Button>
                        </div>
                      ) : item.status === "pending" && item.requested_by === me?.user_id ? (
                        <p className="text-xs text-muted-foreground">Self-review blocked</p>
                      ) : item.status === "pending" ? (
                        <p className="text-xs text-muted-foreground">Review is owner-only.</p>
                      ) : (
                        <p className="text-xs text-muted-foreground">-</p>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
                {roleRequests.length === 0 ? (
                  <TableRow>
                    <TableCell className="px-4 py-4 text-muted-foreground" colSpan={7}>
                      {loadingRoleRequests ? "Loading role requests..." : "No role requests loaded."}
                    </TableCell>
                  </TableRow>
                ) : null}
              </TableBody>
            </Table>
          </div>
        </TabsContent>
      </Tabs>
    </section>
  );
}
