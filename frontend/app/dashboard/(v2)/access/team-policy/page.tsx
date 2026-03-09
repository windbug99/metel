"use client";

import { Select } from "@/components/ui/select";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { useCallback, useEffect, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Loader2 } from "lucide-react";

import { buildNextPath, dashboardApiGet, dashboardApiRequest } from "../../../../../lib/dashboard-v2-client";
import AlertBanner from "../../../../../components/dashboard-v2/alert-banner";
import PageTitleWithTooltip from "@/components/dashboard-v2/page-title-with-tooltip";

type PermissionSnapshot = {
  role: string;
  permissions?: {
    can_manage_teams?: boolean;
  };
};

type TeamItem = {
  id: number;
  name: string;
  description?: string | null;
  is_active: boolean;
  policy_json?: Record<string, unknown>;
  policy_updated_at?: string | null;
};

type TeamMemberItem = {
  id: number;
  user_id: string;
  role: string;
  created_at?: string | null;
};

type TeamRevisionItem = {
  id: number;
  source: string;
  policy_json?: Record<string, unknown>;
  created_by?: string | null;
  created_at?: string | null;
};

function jsonText(value: unknown): string {
  try {
    return JSON.stringify(value ?? {}, null, 2);
  } catch {
    return "{}";
  }
}

function asDate(value?: string | null): string {
  if (!value) {
    return "-";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString();
}

export default function DashboardTeamPolicyPage() {
  const pathname = usePathname();
  const router = useRouter();
  const searchParams = useSearchParams();

  const [permission, setPermission] = useState<PermissionSnapshot | null>(null);
  const [teams, setTeams] = useState<TeamItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [createName, setCreateName] = useState("");
  const [createDescription, setCreateDescription] = useState("");
  const [createPolicy, setCreatePolicy] = useState("{}");
  const [creating, setCreating] = useState(false);

  const [teamNameDraft, setTeamNameDraft] = useState<Record<number, string>>({});
  const [teamDescriptionDraft, setTeamDescriptionDraft] = useState<Record<number, string>>({});
  const [teamPolicyDraft, setTeamPolicyDraft] = useState<Record<number, string>>({});
  const [teamActiveDraft, setTeamActiveDraft] = useState<Record<number, boolean>>({});
  const [savingTeamId, setSavingTeamId] = useState<number | null>(null);

  const [teamMembers, setTeamMembers] = useState<Record<number, TeamMemberItem[]>>({});
  const [teamRevisions, setTeamRevisions] = useState<Record<number, TeamRevisionItem[]>>({});
  const [teamMemberUserDraft, setTeamMemberUserDraft] = useState<Record<number, string>>({});
  const [teamMemberRoleDraft, setTeamMemberRoleDraft] = useState<Record<number, string>>({});
  const [membersLoadingTeamId, setMembersLoadingTeamId] = useState<number | null>(null);
  const [memberSavingTeamId, setMemberSavingTeamId] = useState<number | null>(null);
  const [memberDeletingId, setMemberDeletingId] = useState<number | null>(null);
  const [revisionLoadingTeamId, setRevisionLoadingTeamId] = useState<number | null>(null);
  const [rollbackRevisionId, setRollbackRevisionId] = useState<number | null>(null);

  const canManageTeams = Boolean(permission?.permissions?.can_manage_teams);
  const orgQuery = (searchParams.get("org") ?? "").trim();
  const scopedOrganizationId = orgQuery && orgQuery !== "all" ? Number(orgQuery) : null;

  const handle401 = useCallback(() => {
    const next = encodeURIComponent(buildNextPath(pathname, window.location.search));
    router.replace(`/?next=${next}`);
  }, [pathname, router]);

  const fetchTeams = useCallback(async () => {
    setLoading(true);
    setError(null);

    const meResult = await dashboardApiGet<PermissionSnapshot>("/api/me/permissions");
    if (meResult.status === 401) {
      handle401();
      setLoading(false);
      return;
    }
    if (!meResult.ok || !meResult.data) {
      setError(meResult.error ?? "Failed to load permissions.");
      setLoading(false);
      return;
    }
    setPermission(meResult.data);

    const teamsEndpoint =
      scopedOrganizationId && Number.isFinite(scopedOrganizationId) && scopedOrganizationId > 0
        ? `/api/teams?organization_id=${scopedOrganizationId}`
        : "/api/teams";
    const result = await dashboardApiGet<{ items?: TeamItem[] }>(teamsEndpoint);
    if (result.status === 401) {
      handle401();
      setLoading(false);
      return;
    }
    if (result.status === 403) {
      setError("Access denied while loading teams.");
      setLoading(false);
      return;
    }
    if (!result.ok || !result.data) {
      setError(result.error ?? "Failed to load teams.");
      setLoading(false);
      return;
    }

    const items = Array.isArray(result.data.items) ? result.data.items : [];
    setTeams(items);

    const nextName: Record<number, string> = {};
    const nextDesc: Record<number, string> = {};
    const nextPolicy: Record<number, string> = {};
    const nextActive: Record<number, boolean> = {};
    for (const item of items) {
      nextName[item.id] = item.name ?? "";
      nextDesc[item.id] = item.description ?? "";
      nextPolicy[item.id] = jsonText(item.policy_json ?? {});
      nextActive[item.id] = Boolean(item.is_active);
    }
    setTeamNameDraft(nextName);
    setTeamDescriptionDraft(nextDesc);
    setTeamPolicyDraft(nextPolicy);
    setTeamActiveDraft(nextActive);
    setLoading(false);
  }, [handle401, scopedOrganizationId]);

  const createTeam = useCallback(async () => {
    const name = createName.trim();
    if (!name) {
      setError("Team name is required.");
      return;
    }
    let policyJson: Record<string, unknown> = {};
    try {
      policyJson = JSON.parse((createPolicy || "{}").trim()) as Record<string, unknown>;
    } catch {
      setError("Create policy JSON is invalid.");
      return;
    }

    setCreating(true);
    setError(null);
    const result = await dashboardApiRequest("/api/teams", {
      method: "POST",
      body: {
        name,
        description: createDescription.trim() || null,
        policy_json: policyJson,
        organization_id:
          scopedOrganizationId && Number.isFinite(scopedOrganizationId) && scopedOrganizationId > 0
            ? scopedOrganizationId
            : null,
      },
    });
    if (result.status === 401) {
      handle401();
      setCreating(false);
      return;
    }
    if (result.status === 403) {
      setError("Admin role required to create team.");
      setCreating(false);
      return;
    }
    if (!result.ok) {
      setError(result.error ?? "Failed to create team.");
      setCreating(false);
      return;
    }

    setCreateName("");
    setCreateDescription("");
    setCreatePolicy("{}");
    await fetchTeams();
    setCreating(false);
  }, [createDescription, createName, createPolicy, fetchTeams, handle401, scopedOrganizationId]);

  const updateTeam = useCallback(
    async (teamId: number) => {
      let policyJson: Record<string, unknown> = {};
      try {
        policyJson = JSON.parse((teamPolicyDraft[teamId] || "{}").trim()) as Record<string, unknown>;
      } catch {
        setError(`Team #${teamId} policy JSON is invalid.`);
        return;
      }
      setSavingTeamId(teamId);
      setError(null);
      const result = await dashboardApiRequest(`/api/teams/${teamId}`, {
        method: "PATCH",
        body: {
          name: (teamNameDraft[teamId] ?? "").trim(),
          description: (teamDescriptionDraft[teamId] ?? "").trim() || null,
          is_active: Boolean(teamActiveDraft[teamId]),
          policy_json: policyJson,
        },
      });
      if (result.status === 401) {
        handle401();
        setSavingTeamId(null);
        return;
      }
      if (result.status === 403 || result.status === 404) {
        setError("Admin role required for team updates.");
        setSavingTeamId(null);
        return;
      }
      if (!result.ok) {
        setError(result.error ?? "Failed to update team.");
        setSavingTeamId(null);
        return;
      }
      await fetchTeams();
      setSavingTeamId(null);
    },
    [fetchTeams, handle401, teamActiveDraft, teamDescriptionDraft, teamNameDraft, teamPolicyDraft]
  );

  const loadTeamMembers = useCallback(
    async (teamId: number) => {
      setMembersLoadingTeamId(teamId);
      setError(null);
      const result = await dashboardApiGet<{ items?: TeamMemberItem[] }>(`/api/teams/${teamId}/members`);
      if (result.status === 401) {
        handle401();
        setMembersLoadingTeamId(null);
        return;
      }
      if (result.status === 403 || result.status === 404) {
        setError(`Cannot load members for team #${teamId}.`);
        setMembersLoadingTeamId(null);
        return;
      }
      if (!result.ok || !result.data) {
        setError(result.error ?? "Failed to load team members.");
        setMembersLoadingTeamId(null);
        return;
      }
      const items = Array.isArray(result.data.items) ? result.data.items : [];
      setTeamMembers((prev) => ({ ...prev, [teamId]: items }));
      setMembersLoadingTeamId(null);
    },
    [handle401]
  );

  const upsertTeamMember = useCallback(
    async (teamId: number) => {
      const userId = (teamMemberUserDraft[teamId] ?? "").trim();
      if (!userId) {
        setError("Member user ID or email is required.");
        return;
      }
      setMemberSavingTeamId(teamId);
      setError(null);
      const result = await dashboardApiRequest(`/api/teams/${teamId}/members`, {
        method: "POST",
        body: {
          user_id: userId,
          role: (teamMemberRoleDraft[teamId] ?? "member").trim() || "member",
        },
      });
      if (result.status === 401) {
        handle401();
        setMemberSavingTeamId(null);
        return;
      }
      if (result.status === 403 || result.status === 404) {
        setError("Admin role required for member updates.");
        setMemberSavingTeamId(null);
        return;
      }
      if (!result.ok) {
        setError(result.error ?? "Failed to add/update team member.");
        setMemberSavingTeamId(null);
        return;
      }
      setTeamMemberUserDraft((prev) => ({ ...prev, [teamId]: "" }));
      setTeamMemberRoleDraft((prev) => ({ ...prev, [teamId]: "member" }));
      await loadTeamMembers(teamId);
      setMemberSavingTeamId(null);
    },
    [handle401, loadTeamMembers, teamMemberRoleDraft, teamMemberUserDraft]
  );

  const deleteTeamMember = useCallback(
    async (teamId: number, membershipId: number) => {
      setMemberDeletingId(membershipId);
      setError(null);
      const result = await dashboardApiRequest(`/api/teams/${teamId}/members/${membershipId}`, { method: "DELETE" });
      if (result.status === 401) {
        handle401();
        setMemberDeletingId(null);
        return;
      }
      if (result.status === 403 || result.status === 404) {
        setError("Admin role required for member deletion.");
        setMemberDeletingId(null);
        return;
      }
      if (!result.ok) {
        setError(result.error ?? "Failed to delete team member.");
        setMemberDeletingId(null);
        return;
      }
      await loadTeamMembers(teamId);
      setMemberDeletingId(null);
    },
    [handle401, loadTeamMembers]
  );

  const loadPolicyRevisions = useCallback(
    async (teamId: number) => {
      setRevisionLoadingTeamId(teamId);
      setError(null);
      const result = await dashboardApiGet<{ items?: TeamRevisionItem[] }>(`/api/teams/${teamId}/policy-revisions?limit=20`);
      if (result.status === 401) {
        handle401();
        setRevisionLoadingTeamId(null);
        return;
      }
      if (result.status === 403 || result.status === 404) {
        setError(`Cannot load policy revisions for team #${teamId}.`);
        setRevisionLoadingTeamId(null);
        return;
      }
      if (!result.ok || !result.data) {
        setError(result.error ?? "Failed to load policy revisions.");
        setRevisionLoadingTeamId(null);
        return;
      }
      const items = Array.isArray(result.data.items) ? result.data.items : [];
      setTeamRevisions((prev) => ({ ...prev, [teamId]: items }));
      setRevisionLoadingTeamId(null);
    },
    [handle401]
  );

  const rollbackRevision = useCallback(
    async (teamId: number, revisionId: number) => {
      setRollbackRevisionId(revisionId);
      setError(null);
      const result = await dashboardApiRequest(`/api/teams/${teamId}/policy-revisions/${revisionId}/rollback`, { method: "POST" });
      if (result.status === 401) {
        handle401();
        setRollbackRevisionId(null);
        return;
      }
      if (result.status === 403 || result.status === 404) {
        setError("Admin role required for policy rollback.");
        setRollbackRevisionId(null);
        return;
      }
      if (!result.ok) {
        setError(result.error ?? "Failed to rollback policy revision.");
        setRollbackRevisionId(null);
        return;
      }
      await Promise.all([fetchTeams(), loadPolicyRevisions(teamId)]);
      setRollbackRevisionId(null);
    },
    [fetchTeams, handle401, loadPolicyRevisions]
  );

  useEffect(() => {
    void fetchTeams();
  }, [fetchTeams]);

  useEffect(() => {
    const handler = (event: Event) => {
      const custom = event as CustomEvent<{ path?: string }>;
      if (custom.detail?.path === pathname) {
        void fetchTeams();
      }
    };
    window.addEventListener("dashboard:v2:refresh", handler as EventListener);
    return () => {
      window.removeEventListener("dashboard:v2:refresh", handler as EventListener);
    };
  }, [fetchTeams, pathname]);

  if (loading) {
    return (
      <section className="space-y-4">
        <PageTitleWithTooltip title="Team Policy" tooltip="Create teams, manage memberships, and edit team policy revisions." />
        <p className="text-sm text-muted-foreground">Create teams, manage memberships, and control team policy revisions.</p>
        <div className="ds-card flex min-h-[220px] items-center justify-center p-4">
          <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
        </div>
      </section>
    );
  }

  return (
    <section className="space-y-4">
      <PageTitleWithTooltip title="Team Policy" tooltip="Create teams, manage memberships, and edit team policy revisions." />
      <p className="text-sm text-muted-foreground">Create teams, manage memberships, and control team policy revisions.</p>

      {error ? <AlertBanner message={error} tone="danger" /> : null}
      <div className="ds-card p-4">
        <p className="mb-2 text-sm font-semibold">Create team</p>
        <div className="space-y-2">
          <div className="grid gap-2 md:grid-cols-2">
            <Input
              value={createName}
              onChange={(event) => setCreateName(event.target.value)}
              placeholder="Team name"
              className="ds-input h-11 w-full rounded-md px-3 text-sm md:h-9"
            />
            <Input
              value={createDescription}
              onChange={(event) => setCreateDescription(event.target.value)}
              placeholder="Description (optional)"
              className="ds-input h-11 w-full rounded-md px-3 text-sm md:h-9"
            />
          </div>
          <textarea
            value={createPolicy}
            onChange={(event) => setCreatePolicy(event.target.value)}
            className="ds-input min-h-[120px] w-full rounded-md px-3 py-2 text-xs font-mono"
          />
          <Button
            type="button"
            onClick={() => void createTeam()}
            disabled={!canManageTeams || creating}
            className="ds-btn h-11 rounded-md px-3 text-sm disabled:cursor-not-allowed disabled:opacity-60 md:h-9"
            title={canManageTeams ? "" : "Admin role required"}
          >
            {creating ? "Creating..." : "Create Team"}
          </Button>
          {!canManageTeams ? <p className="text-xs text-muted-foreground">Admin role required.</p> : null}
        </div>
      </div>

      {teams.map((team) => (
        <article key={team.id} className="ds-card space-y-3 p-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <p className="text-base font-semibold">Team #{team.id}</p>
              <p className="text-xs text-muted-foreground">policy updated {asDate(team.policy_updated_at)}</p>
            </div>
            <label className="flex items-center gap-2 text-xs">
              <Checkbox
                checked={Boolean(teamActiveDraft[team.id])}
                onCheckedChange={(checked) =>
                  setTeamActiveDraft((prev) => ({
                    ...prev,
                    [team.id]: checked,
                  }))
                }
              />
              active
            </label>
          </div>

          <div className="grid gap-2 md:grid-cols-2">
            <Input
              value={teamNameDraft[team.id] ?? ""}
              onChange={(event) => setTeamNameDraft((prev) => ({ ...prev, [team.id]: event.target.value }))}
              className="ds-input h-11 w-full rounded-md px-3 text-sm md:h-9"
            />
            <Input
              value={teamDescriptionDraft[team.id] ?? ""}
              onChange={(event) => setTeamDescriptionDraft((prev) => ({ ...prev, [team.id]: event.target.value }))}
              className="ds-input h-11 w-full rounded-md px-3 text-sm md:h-9"
            />
          </div>
          <textarea
            value={teamPolicyDraft[team.id] ?? "{}"}
            onChange={(event) => setTeamPolicyDraft((prev) => ({ ...prev, [team.id]: event.target.value }))}
            className="ds-input min-h-[120px] w-full rounded-md px-3 py-2 text-xs font-mono"
          />
          <div className="flex flex-wrap items-center gap-2">
            <Button
              type="button"
              onClick={() => void updateTeam(team.id)}
              disabled={!canManageTeams || savingTeamId === team.id}
              className="ds-btn h-11 rounded-md px-3 text-sm disabled:cursor-not-allowed disabled:opacity-60 md:h-9"
              title={canManageTeams ? "" : "Admin role required"}
            >
              {savingTeamId === team.id ? "Saving..." : "Save Team Policy"}
            </Button>
            <Button
              type="button"
              onClick={() => void loadPolicyRevisions(team.id)}
              disabled={revisionLoadingTeamId === team.id}
              className="ds-btn h-11 rounded-md px-3 text-sm disabled:cursor-not-allowed disabled:opacity-60 md:h-9"
            >
              {revisionLoadingTeamId === team.id ? "Loading..." : "Load Revisions"}
            </Button>
            <Button
              type="button"
              onClick={() => void loadTeamMembers(team.id)}
              disabled={membersLoadingTeamId === team.id}
              className="ds-btn h-11 rounded-md px-3 text-sm disabled:cursor-not-allowed disabled:opacity-60 md:h-9"
            >
              {membersLoadingTeamId === team.id ? "Loading..." : "Load Members"}
            </Button>
          </div>

          {(teamRevisions[team.id] ?? []).length > 0 ? (
            <div className="rounded-md border border-border p-3">
              <p className="mb-2 text-sm font-medium">Policy revisions</p>
              <div className="space-y-2">
                {(teamRevisions[team.id] ?? []).slice(0, 10).map((revision) => (
                  <div key={`team-revision-${revision.id}`} className="rounded-md border border-border p-2">
                    <p className="text-xs">
                      #{revision.id} · {revision.source} · {asDate(revision.created_at)}
                    </p>
                    <pre className="mt-1 overflow-x-auto rounded bg-muted/60 p-2 text-[11px]">
                      {jsonText(revision.policy_json ?? {})}
                    </pre>
                    <Button
                      type="button"
                      onClick={() => void rollbackRevision(team.id, revision.id)}
                      disabled={!canManageTeams || rollbackRevisionId === revision.id}
                      className="ds-btn mt-2 h-10 rounded-md px-3 text-xs disabled:cursor-not-allowed disabled:opacity-60"
                      title={canManageTeams ? "" : "Admin role required"}
                    >
                      {rollbackRevisionId === revision.id ? "Rolling back..." : "Rollback"}
                    </Button>
                  </div>
                ))}
              </div>
            </div>
          ) : null}

          <div className="rounded-md border border-border p-3">
            <p className="mb-2 text-sm font-medium">Members</p>
            <div className="mb-2 grid items-center gap-2 lg:grid-cols-[minmax(260px,1fr)_140px_auto]">
              <Input
                value={teamMemberUserDraft[team.id] ?? ""}
                onChange={(event) => setTeamMemberUserDraft((prev) => ({ ...prev, [team.id]: event.target.value }))}
                placeholder="User ID or Email"
                className="ds-input h-11 w-full rounded-md px-3 text-sm md:h-9"
              />
              <Select
                value={teamMemberRoleDraft[team.id] ?? "member"}
                onChange={(event) => setTeamMemberRoleDraft((prev) => ({ ...prev, [team.id]: event.target.value }))}
                className="ds-input h-11 w-full rounded-md px-3 text-sm md:h-9"
              >
                <option value="owner">owner</option>
                <option value="admin">admin</option>
                <option value="member">member</option>
              </Select>
              <Button
                type="button"
                onClick={() => void upsertTeamMember(team.id)}
                disabled={!canManageTeams || memberSavingTeamId === team.id}
                className="ds-btn h-11 whitespace-nowrap rounded-md px-3 text-sm disabled:cursor-not-allowed disabled:opacity-60 md:h-9"
                title={canManageTeams ? "" : "Admin role required"}
              >
                {memberSavingTeamId === team.id ? "Saving..." : "Add / Update Member"}
              </Button>
            </div>

            <div className="space-y-2">
              {(teamMembers[team.id] ?? []).map((member) => (
                <div key={`team-${team.id}-member-${member.id}`} className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-border px-3 py-2">
                  <p className="text-xs">
                    #{member.id} · {member.user_id} · {member.role} · {asDate(member.created_at)}
                  </p>
                  <Button
                    type="button"
                    onClick={() => void deleteTeamMember(team.id, member.id)}
                    disabled={!canManageTeams || memberDeletingId === member.id}
                    className="ds-btn h-10 rounded-md px-3 text-xs disabled:cursor-not-allowed disabled:opacity-60"
                    title={canManageTeams ? "" : "Admin role required"}
                  >
                    {memberDeletingId === member.id ? "Deleting..." : "Delete"}
                  </Button>
                </div>
              ))}
              {(teamMembers[team.id] ?? []).length === 0 ? <p className="text-xs text-muted-foreground">No members loaded.</p> : null}
            </div>
          </div>
        </article>
      ))}

      {!loading && teams.length === 0 ? <p className="text-sm text-muted-foreground">No teams found.</p> : null}
    </section>
  );
}
