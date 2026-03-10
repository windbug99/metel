"use client";

import { Select } from "@/components/ui/select";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useCallback, useEffect, useMemo, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { ChevronsUpDown, Loader2 } from "lucide-react";

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

type ToolOptionItem = {
  tool_name: string;
  service: string;
};

type PolicyMode = "basic" | "advanced";

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

function parseCsvList(value: string): string[] {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter((item) => item.length > 0);
}

function csvHasValue(csv: string, value: string): boolean {
  const normalized = value.trim();
  if (!normalized) {
    return false;
  }
  return parseCsvList(csv).includes(normalized);
}

function updateCsvSelection(csv: string, value: string, checked: boolean): string {
  const normalized = value.trim();
  if (!normalized) {
    return csv;
  }
  const current = parseCsvList(csv);
  const next = checked ? Array.from(new Set([...current, normalized])) : current.filter((item) => item !== normalized);
  return next.join(", ");
}

function toolsDropdownLabel(csv: string, emptyLabel = "Deny tools: None"): string {
  const selected = parseCsvList(csv);
  if (selected.length === 0) {
    return emptyLabel;
  }
  if (selected.length === 1) {
    return `Deny tools: ${selected[0]}`;
  }
  return `Deny tools: ${selected[0]} +${selected.length - 1}`;
}

function parsePolicyObject(text: string): Record<string, unknown> {
  const parsed = JSON.parse((text || "{}").trim()) as unknown;
  if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error("Policy JSON must be an object.");
  }
  return parsed as Record<string, unknown>;
}

function buildPolicyFromBasic(
  allowedServices: string[],
  denyToolsCsv: string,
  allowHighRisk: boolean,
  linearTeamIdsCsv: string
): Record<string, unknown> {
  const policy: Record<string, unknown> = {};
  const services = allowedServices
    .map((item) => item.trim().toLowerCase())
    .filter((item) => item === "notion" || item === "linear");
  if (services.length > 0) {
    policy.allowed_services = Array.from(new Set(services));
  }
  const denyTools = parseCsvList(denyToolsCsv);
  if (denyTools.length > 0) {
    policy.deny_tools = denyTools;
  }
  if (allowHighRisk) {
    policy.allow_high_risk = true;
  }
  const linearTeamIds = parseCsvList(linearTeamIdsCsv);
  if (linearTeamIds.length > 0) {
    policy.allowed_linear_team_ids = linearTeamIds;
  }
  return policy;
}

function parseBasicFromPolicy(policy: Record<string, unknown> | null | undefined): {
  allowedServices: string[];
  denyToolsCsv: string;
  allowHighRisk: boolean;
  linearTeamIdsCsv: string;
} {
  const source = policy && typeof policy === "object" ? policy : {};

  const allowedServicesRaw = source.allowed_services;
  const allowedServices = Array.isArray(allowedServicesRaw)
    ? allowedServicesRaw
        .map((item) => String(item || "").trim().toLowerCase())
        .filter((item) => item === "notion" || item === "linear")
    : [];

  const denyToolsRaw = source.deny_tools;
  const denyToolsCsv = Array.isArray(denyToolsRaw)
    ? denyToolsRaw
        .map((item) => String(item || "").trim())
        .filter((item) => item.length > 0)
        .join(", ")
    : "";

  const allowHighRisk = Boolean(source.allow_high_risk);

  const linearIdsRaw = source.allowed_linear_team_ids;
  const linearTeamIdsCsv = Array.isArray(linearIdsRaw)
    ? linearIdsRaw
        .map((item) => String(item || "").trim())
        .filter((item) => item.length > 0)
        .join(", ")
    : "";

  return { allowedServices, denyToolsCsv, allowHighRisk, linearTeamIdsCsv };
}

export default function DashboardTeamPolicyPage() {
  const pathname = usePathname();
  const router = useRouter();
  const searchParams = useSearchParams();

  const [permission, setPermission] = useState<PermissionSnapshot | null>(null);
  const [teams, setTeams] = useState<TeamItem[]>([]);
  const [toolOptions, setToolOptions] = useState<ToolOptionItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [createDialogOpen, setCreateDialogOpen] = useState(false);
  const [createName, setCreateName] = useState("");
  const [createDescription, setCreateDescription] = useState("");
  const [createPolicy, setCreatePolicy] = useState("{}");
  const [createPolicyMode, setCreatePolicyMode] = useState<PolicyMode>("basic");
  const [createPolicyAllowedServices, setCreatePolicyAllowedServices] = useState<string[]>([]);
  const [createPolicyDenyTools, setCreatePolicyDenyTools] = useState("");
  const [createPolicyAllowHighRisk, setCreatePolicyAllowHighRisk] = useState(false);
  const [createPolicyLinearTeamIds, setCreatePolicyLinearTeamIds] = useState("");
  const [creating, setCreating] = useState(false);

  const [teamNameDraft, setTeamNameDraft] = useState<Record<number, string>>({});
  const [teamDescriptionDraft, setTeamDescriptionDraft] = useState<Record<number, string>>({});
  const [teamPolicyDraft, setTeamPolicyDraft] = useState<Record<number, string>>({});
  const [teamPolicyModeDraft, setTeamPolicyModeDraft] = useState<Record<number, PolicyMode>>({});
  const [teamPolicyAllowedServicesDraft, setTeamPolicyAllowedServicesDraft] = useState<Record<number, string[]>>({});
  const [teamPolicyDenyToolsDraft, setTeamPolicyDenyToolsDraft] = useState<Record<number, string>>({});
  const [teamPolicyAllowHighRiskDraft, setTeamPolicyAllowHighRiskDraft] = useState<Record<number, boolean>>({});
  const [teamPolicyLinearTeamIdsDraft, setTeamPolicyLinearTeamIdsDraft] = useState<Record<number, string>>({});
  const [teamActiveDraft, setTeamActiveDraft] = useState<Record<number, boolean>>({});
  const [savingTeamId, setSavingTeamId] = useState<number | null>(null);

  const [teamMembers, setTeamMembers] = useState<Record<number, TeamMemberItem[]>>({});
  const [teamRevisions, setTeamRevisions] = useState<Record<number, TeamRevisionItem[]>>({});
  const [teamMemberUserDraft, setTeamMemberUserDraft] = useState<Record<number, string>>({});
  const [teamMemberRoleDraft, setTeamMemberRoleDraft] = useState<Record<number, string>>({});
  const [memberSavingTeamId, setMemberSavingTeamId] = useState<number | null>(null);
  const [memberDeletingId, setMemberDeletingId] = useState<number | null>(null);
  const [rollbackRevisionId, setRollbackRevisionId] = useState<number | null>(null);

  const [membersLoadingByTeam, setMembersLoadingByTeam] = useState<Record<number, boolean>>({});
  const [revisionsLoadingByTeam, setRevisionsLoadingByTeam] = useState<Record<number, boolean>>({});
  const [membersLoadedByTeam, setMembersLoadedByTeam] = useState<Record<number, boolean>>({});
  const [revisionsLoadedByTeam, setRevisionsLoadedByTeam] = useState<Record<number, boolean>>({});

  const canManageTeams = Boolean(permission?.permissions?.can_manage_teams);
  const orgQuery = (searchParams.get("org") ?? "").trim();
  const scopedOrganizationId = orgQuery && orgQuery !== "all" ? Number(orgQuery) : null;

  const allToolNamesCsv = useMemo(
    () => Array.from(new Set(toolOptions.map((tool) => tool.tool_name.trim()).filter((name) => name.length > 0))).join(", "),
    [toolOptions]
  );

  const createPolicyPreview = useMemo(
    () => buildPolicyFromBasic(createPolicyAllowedServices, createPolicyDenyTools, createPolicyAllowHighRisk, createPolicyLinearTeamIds),
    [createPolicyAllowedServices, createPolicyDenyTools, createPolicyAllowHighRisk, createPolicyLinearTeamIds]
  );

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

    const [teamsResult, toolsResult] = await Promise.all([
      dashboardApiGet<{ items?: TeamItem[] }>(teamsEndpoint),
      dashboardApiGet<{ items?: ToolOptionItem[] }>("/api/api-keys/tool-options"),
    ]);

    if (teamsResult.status === 401 || toolsResult.status === 401) {
      handle401();
      setLoading(false);
      return;
    }
    if (teamsResult.status === 403) {
      setError("Access denied while loading teams.");
      setLoading(false);
      return;
    }
    if (!teamsResult.ok || !teamsResult.data) {
      setError(teamsResult.error ?? "Failed to load teams.");
      setLoading(false);
      return;
    }

    const items = Array.isArray(teamsResult.data.items) ? teamsResult.data.items : [];
    setTeams(items);

    if (toolsResult.ok && toolsResult.data) {
      setToolOptions(Array.isArray(toolsResult.data.items) ? toolsResult.data.items : []);
    }

    const nextName: Record<number, string> = {};
    const nextDesc: Record<number, string> = {};
    const nextPolicy: Record<number, string> = {};
    const nextMode: Record<number, PolicyMode> = {};
    const nextAllowedServices: Record<number, string[]> = {};
    const nextDenyTools: Record<number, string> = {};
    const nextAllowHighRisk: Record<number, boolean> = {};
    const nextLinearTeamIds: Record<number, string> = {};
    const nextActive: Record<number, boolean> = {};

    for (const item of items) {
      nextName[item.id] = item.name ?? "";
      nextDesc[item.id] = item.description ?? "";
      nextPolicy[item.id] = jsonText(item.policy_json ?? {});
      nextMode[item.id] = "basic";
      const parsed = parseBasicFromPolicy(item.policy_json ?? {});
      nextAllowedServices[item.id] = parsed.allowedServices;
      nextDenyTools[item.id] = parsed.denyToolsCsv;
      nextAllowHighRisk[item.id] = parsed.allowHighRisk;
      nextLinearTeamIds[item.id] = parsed.linearTeamIdsCsv;
      nextActive[item.id] = Boolean(item.is_active);
    }

    setTeamNameDraft(nextName);
    setTeamDescriptionDraft(nextDesc);
    setTeamPolicyDraft(nextPolicy);
    setTeamPolicyModeDraft(nextMode);
    setTeamPolicyAllowedServicesDraft(nextAllowedServices);
    setTeamPolicyDenyToolsDraft(nextDenyTools);
    setTeamPolicyAllowHighRiskDraft(nextAllowHighRisk);
    setTeamPolicyLinearTeamIdsDraft(nextLinearTeamIds);
    setTeamActiveDraft(nextActive);
    setLoading(false);
  }, [handle401, scopedOrganizationId]);

  const syncTeamPolicyJsonFromBasic = useCallback((teamId: number, allowedServices: string[], denyToolsCsv: string, allowHighRisk: boolean, linearTeamIdsCsv: string) => {
    const nextPolicy = buildPolicyFromBasic(allowedServices, denyToolsCsv, allowHighRisk, linearTeamIdsCsv);
    setTeamPolicyDraft((prev) => ({ ...prev, [teamId]: jsonText(nextPolicy) }));
  }, []);

  const applyCreateAdvancedToBasic = useCallback(() => {
    try {
      const parsed = parsePolicyObject(createPolicy);
      const basic = parseBasicFromPolicy(parsed);
      setCreatePolicyAllowedServices(basic.allowedServices);
      setCreatePolicyDenyTools(basic.denyToolsCsv);
      setCreatePolicyAllowHighRisk(basic.allowHighRisk);
      setCreatePolicyLinearTeamIds(basic.linearTeamIdsCsv);
      setError(null);
    } catch (applyError) {
      setError(applyError instanceof Error ? applyError.message : "Invalid policy JSON.");
    }
  }, [createPolicy]);

  const applyTeamAdvancedToBasic = useCallback(
    (teamId: number) => {
      try {
        const parsed = parsePolicyObject(teamPolicyDraft[teamId] ?? "{}");
        const basic = parseBasicFromPolicy(parsed);
        setTeamPolicyAllowedServicesDraft((prev) => ({ ...prev, [teamId]: basic.allowedServices }));
        setTeamPolicyDenyToolsDraft((prev) => ({ ...prev, [teamId]: basic.denyToolsCsv }));
        setTeamPolicyAllowHighRiskDraft((prev) => ({ ...prev, [teamId]: basic.allowHighRisk }));
        setTeamPolicyLinearTeamIdsDraft((prev) => ({ ...prev, [teamId]: basic.linearTeamIdsCsv }));
        setError(null);
      } catch (applyError) {
        setError(applyError instanceof Error ? applyError.message : "Invalid policy JSON.");
      }
    },
    [teamPolicyDraft]
  );

  const loadTeamMembers = useCallback(
    async (teamId: number) => {
      if (membersLoadingByTeam[teamId]) {
        return;
      }
      setMembersLoadingByTeam((prev) => ({ ...prev, [teamId]: true }));
      setError(null);
      const result = await dashboardApiGet<{ items?: TeamMemberItem[] }>(`/api/teams/${teamId}/members`);
      if (result.status === 401) {
        handle401();
        setMembersLoadingByTeam((prev) => ({ ...prev, [teamId]: false }));
        return;
      }
      if (result.status === 403 || result.status === 404) {
        setError(`Cannot load members for team #${teamId}.`);
        setMembersLoadingByTeam((prev) => ({ ...prev, [teamId]: false }));
        return;
      }
      if (!result.ok || !result.data) {
        setError(result.error ?? "Failed to load team members.");
        setMembersLoadingByTeam((prev) => ({ ...prev, [teamId]: false }));
        return;
      }
      const items = Array.isArray(result.data.items) ? result.data.items : [];
      setTeamMembers((prev) => ({ ...prev, [teamId]: items }));
      setMembersLoadedByTeam((prev) => ({ ...prev, [teamId]: true }));
      setMembersLoadingByTeam((prev) => ({ ...prev, [teamId]: false }));
    },
    [handle401, membersLoadingByTeam]
  );

  const loadPolicyRevisions = useCallback(
    async (teamId: number) => {
      if (revisionsLoadingByTeam[teamId]) {
        return;
      }
      setRevisionsLoadingByTeam((prev) => ({ ...prev, [teamId]: true }));
      setError(null);
      const result = await dashboardApiGet<{ items?: TeamRevisionItem[] }>(`/api/teams/${teamId}/policy-revisions?limit=20`);
      if (result.status === 401) {
        handle401();
        setRevisionsLoadingByTeam((prev) => ({ ...prev, [teamId]: false }));
        return;
      }
      if (result.status === 403 || result.status === 404) {
        setError(`Cannot load policy revisions for team #${teamId}.`);
        setRevisionsLoadingByTeam((prev) => ({ ...prev, [teamId]: false }));
        return;
      }
      if (!result.ok || !result.data) {
        setError(result.error ?? "Failed to load policy revisions.");
        setRevisionsLoadingByTeam((prev) => ({ ...prev, [teamId]: false }));
        return;
      }
      const items = Array.isArray(result.data.items) ? result.data.items : [];
      setTeamRevisions((prev) => ({ ...prev, [teamId]: items }));
      setRevisionsLoadedByTeam((prev) => ({ ...prev, [teamId]: true }));
      setRevisionsLoadingByTeam((prev) => ({ ...prev, [teamId]: false }));
    },
    [handle401, revisionsLoadingByTeam]
  );

  const createTeam = useCallback(async () => {
    const name = createName.trim();
    if (!name) {
      setError("Team name is required.");
      return;
    }

    let policyJson: Record<string, unknown> = {};
    if (createPolicyMode === "advanced") {
      try {
        policyJson = parsePolicyObject(createPolicy);
      } catch (parseError) {
        setError(parseError instanceof Error ? parseError.message : "Create policy JSON is invalid.");
        return;
      }
    } else {
      if (parseCsvList(createPolicyLinearTeamIds).length > 0 && !createPolicyAllowedServices.includes("linear")) {
        setError("If you set linear team IDs, select linear in allowed services.");
        return;
      }
      policyJson = buildPolicyFromBasic(
        createPolicyAllowedServices,
        createPolicyDenyTools,
        createPolicyAllowHighRisk,
        createPolicyLinearTeamIds
      );
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
    setCreatePolicyMode("basic");
    setCreatePolicyAllowedServices([]);
    setCreatePolicyDenyTools("");
    setCreatePolicyAllowHighRisk(false);
    setCreatePolicyLinearTeamIds("");
    setCreateDialogOpen(false);
    await fetchTeams();
    setCreating(false);
  }, [
    createDescription,
    createName,
    createPolicy,
    createPolicyAllowHighRisk,
    createPolicyAllowedServices,
    createPolicyDenyTools,
    createPolicyLinearTeamIds,
    createPolicyMode,
    fetchTeams,
    handle401,
    scopedOrganizationId,
  ]);

  const updateTeam = useCallback(
    async (teamId: number) => {
      let policyJson: Record<string, unknown> = {};
      const mode = teamPolicyModeDraft[teamId] ?? "basic";
      if (mode === "advanced") {
        try {
          policyJson = parsePolicyObject(teamPolicyDraft[teamId] ?? "{}");
        } catch (parseError) {
          setError(parseError instanceof Error ? parseError.message : `Team #${teamId} policy JSON is invalid.`);
          return;
        }
      } else {
        const allowedServices = teamPolicyAllowedServicesDraft[teamId] ?? [];
        const denyToolsCsv = teamPolicyDenyToolsDraft[teamId] ?? "";
        const allowHighRisk = Boolean(teamPolicyAllowHighRiskDraft[teamId]);
        const linearTeamIds = teamPolicyLinearTeamIdsDraft[teamId] ?? "";
        if (parseCsvList(linearTeamIds).length > 0 && !allowedServices.includes("linear")) {
          setError(`Team #${teamId}: select linear in allowed services when using linear team IDs.`);
          return;
        }
        policyJson = buildPolicyFromBasic(allowedServices, denyToolsCsv, allowHighRisk, linearTeamIds);
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
    [
      fetchTeams,
      handle401,
      teamActiveDraft,
      teamDescriptionDraft,
      teamNameDraft,
      teamPolicyAllowHighRiskDraft,
      teamPolicyAllowedServicesDraft,
      teamPolicyDenyToolsDraft,
      teamPolicyDraft,
      teamPolicyLinearTeamIdsDraft,
      teamPolicyModeDraft,
    ]
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

  useEffect(() => {
    for (const team of teams) {
      if (!membersLoadedByTeam[team.id] && !membersLoadingByTeam[team.id]) {
        void loadTeamMembers(team.id);
      }
      if (!revisionsLoadedByTeam[team.id] && !revisionsLoadingByTeam[team.id]) {
        void loadPolicyRevisions(team.id);
      }
    }
  }, [
    loadPolicyRevisions,
    loadTeamMembers,
    membersLoadedByTeam,
    membersLoadingByTeam,
    revisionsLoadedByTeam,
    revisionsLoadingByTeam,
    teams,
  ]);

  const visibleTeams = useMemo(() => teams, [teams]);

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

      <div className="flex items-center justify-end">
        <Button
          type="button"
          onClick={() => setCreateDialogOpen(true)}
          disabled={!canManageTeams}
          className="ds-btn h-11 rounded-md px-4 text-sm disabled:cursor-not-allowed disabled:opacity-60 md:h-9"
          title={canManageTeams ? "" : "Admin role required"}
        >
          Create Team
        </Button>
      </div>

      <Dialog
        open={createDialogOpen}
        onOpenChange={(open) => {
          if (!creating) {
            setCreateDialogOpen(open);
          }
        }}
      >
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>Create Team</DialogTitle>
            <DialogDescription>Create a team and configure policy in Basic mode (recommended).</DialogDescription>
          </DialogHeader>
          <div className="space-y-3 py-2">
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

            <Tabs value={createPolicyMode} onValueChange={(value) => setCreatePolicyMode(value === "advanced" ? "advanced" : "basic")}>
              <TabsList className="h-9">
                <TabsTrigger value="basic" className="px-3 py-1 text-xs">Basic</TabsTrigger>
                <TabsTrigger value="advanced" className="px-3 py-1 text-xs">Advanced JSON</TabsTrigger>
              </TabsList>

              <TabsContent value="basic" className="space-y-2">
                <div className="grid gap-2 md:grid-cols-2">
                  <div className="rounded-md border border-border p-2">
                    <p className="mb-1 text-xs text-muted-foreground">Allowed services</p>
                    <div className="flex flex-wrap gap-3">
                      <label className="flex items-center gap-2 text-sm">
                        <Checkbox
                          checked={createPolicyAllowedServices.includes("notion")}
                          onCheckedChange={(checked) => {
                            const next = checked
                              ? Array.from(new Set([...createPolicyAllowedServices, "notion"]))
                              : createPolicyAllowedServices.filter((item) => item !== "notion");
                            setCreatePolicyAllowedServices(next);
                          }}
                        />
                        notion
                      </label>
                      <label className="flex items-center gap-2 text-sm">
                        <Checkbox
                          checked={createPolicyAllowedServices.includes("linear")}
                          onCheckedChange={(checked) => {
                            const next = checked
                              ? Array.from(new Set([...createPolicyAllowedServices, "linear"]))
                              : createPolicyAllowedServices.filter((item) => item !== "linear");
                            setCreatePolicyAllowedServices(next);
                          }}
                        />
                        linear
                      </label>
                    </div>
                  </div>

                  <div className="rounded-md border border-border p-2">
                    <p className="mb-1 text-xs text-muted-foreground">Risk</p>
                    <label className="flex items-center gap-2 text-sm">
                      <Checkbox checked={createPolicyAllowHighRisk} onCheckedChange={(checked) => setCreatePolicyAllowHighRisk(checked === true)} />
                      Allow high risk
                    </label>
                  </div>
                </div>

                <div className="grid gap-2 md:grid-cols-2">
                  <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                      <Button type="button" variant="outline" className="h-11 justify-between rounded-md px-3 text-sm md:h-9">
                        {toolsDropdownLabel(createPolicyDenyTools)}
                        <ChevronsUpDown className="h-4 w-4 opacity-70" />
                      </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent className="w-[340px] max-w-[90vw]" align="start">
                      {toolOptions.length === 0 ? <div className="px-2 py-1 text-xs text-muted-foreground">No tools found.</div> : null}
                      {toolOptions.map((tool, index) => {
                        const checked = csvHasValue(createPolicyDenyTools, tool.tool_name);
                        return (
                          <div key={`create-team-policy-deny-${tool.tool_name}`}>
                            <DropdownMenuCheckboxItem
                              checked={checked}
                              onCheckedChange={(nextChecked) => {
                                setCreatePolicyDenyTools((prev) => updateCsvSelection(prev, tool.tool_name, nextChecked === true));
                              }}
                            >
                              {tool.tool_name} ({tool.service})
                            </DropdownMenuCheckboxItem>
                            {index < toolOptions.length - 1 ? <DropdownMenuSeparator /> : null}
                          </div>
                        );
                      })}
                    </DropdownMenuContent>
                  </DropdownMenu>

                  <Input
                    value={createPolicyLinearTeamIds}
                    onChange={(event) => setCreatePolicyLinearTeamIds(event.target.value)}
                    placeholder="Allowed Linear team IDs CSV (optional)"
                    className="ds-input h-11 w-full rounded-md px-3 text-sm md:h-9"
                  />
                </div>

                <div className="rounded-md border border-border p-2">
                  <p className="mb-1 text-xs text-muted-foreground">Policy JSON preview</p>
                  <pre className="max-h-44 overflow-auto rounded bg-muted/60 p-2 text-[11px]">{jsonText(createPolicyPreview)}</pre>
                </div>
                {allToolNamesCsv ? <p className="text-xs text-muted-foreground">Available tools: {allToolNamesCsv}</p> : null}
              </TabsContent>

              <TabsContent value="advanced" className="space-y-2">
                <textarea
                  value={createPolicy}
                  onChange={(event) => setCreatePolicy(event.target.value)}
                  className="ds-input min-h-[180px] w-full rounded-md px-3 py-2 text-xs font-mono"
                  placeholder='Policy JSON, e.g. {"deny_tools":["notion_delete_block"]}'
                />
                <Button type="button" variant="outline" onClick={applyCreateAdvancedToBasic} className="h-9 rounded-md px-3 text-xs">
                  Apply JSON to Basic
                </Button>
              </TabsContent>
            </Tabs>
          </div>
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => setCreateDialogOpen(false)}
              disabled={creating}
              className="h-11 rounded-md px-4 text-sm md:h-9"
            >
              Cancel
            </Button>
            <Button
              type="button"
              onClick={() => void createTeam()}
              disabled={!canManageTeams || creating}
              className="ds-btn h-11 rounded-md px-4 text-sm disabled:cursor-not-allowed disabled:opacity-60 md:h-9"
              title={canManageTeams ? "" : "Admin role required"}
            >
              {creating ? "Creating..." : "Create Team"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {visibleTeams.map((team) => {
        const policyMode = teamPolicyModeDraft[team.id] ?? "basic";
        const teamPolicyPreview = buildPolicyFromBasic(
          teamPolicyAllowedServicesDraft[team.id] ?? [],
          teamPolicyDenyToolsDraft[team.id] ?? "",
          Boolean(teamPolicyAllowHighRiskDraft[team.id]),
          teamPolicyLinearTeamIdsDraft[team.id] ?? ""
        );

        return (
          <article key={team.id} className="ds-card space-y-3 p-4">
            <div className="flex flex-wrap items-start justify-between gap-2">
              <div>
                <p className="text-base font-semibold">{teamNameDraft[team.id] || team.name}</p>
                <p className="text-xs text-muted-foreground">{teamDescriptionDraft[team.id] || "No description"}</p>
                <p className="mt-1 text-xs text-muted-foreground">policy updated {asDate(team.policy_updated_at)}</p>
              </div>
              <p className="text-xs text-muted-foreground">Team #{team.id}</p>
            </div>

            <Tabs defaultValue="members" className="space-y-3">
              <TabsList className="h-9">
                <TabsTrigger value="members" className="px-3 py-1 text-xs">Members</TabsTrigger>
                <TabsTrigger value="revisions" className="px-3 py-1 text-xs">Revisions</TabsTrigger>
                <TabsTrigger value="policy" className="px-3 py-1 text-xs">Policy</TabsTrigger>
              </TabsList>

              <TabsContent value="members" className="space-y-3">
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

                  {membersLoadingByTeam[team.id] ? <p className="mb-2 text-xs text-muted-foreground">Loading members...</p> : null}

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
                    {(teamMembers[team.id] ?? []).length === 0 && !membersLoadingByTeam[team.id] ? (
                      <p className="text-xs text-muted-foreground">No members.</p>
                    ) : null}
                  </div>
                </div>
              </TabsContent>

              <TabsContent value="revisions" className="space-y-3">
                <div className="rounded-md border border-border p-3">
                  <p className="mb-2 text-sm font-medium">Policy revisions</p>
                  {revisionsLoadingByTeam[team.id] ? <p className="mb-2 text-xs text-muted-foreground">Loading revisions...</p> : null}
                  {(teamRevisions[team.id] ?? []).length > 0 ? (
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
                  ) : null}
                  {(teamRevisions[team.id] ?? []).length === 0 && !revisionsLoadingByTeam[team.id] ? (
                    <p className="text-xs text-muted-foreground">No revisions.</p>
                  ) : null}
                </div>
              </TabsContent>

              <TabsContent value="policy" className="space-y-3">
                <div className="rounded-md border border-border p-3">
                  <p className="mb-2 text-sm font-medium">Team policy</p>
                  <div className="mb-2 grid gap-2 md:grid-cols-2">
                    <Input
                      value={teamNameDraft[team.id] ?? ""}
                      onChange={(event) => setTeamNameDraft((prev) => ({ ...prev, [team.id]: event.target.value }))}
                      className="ds-input h-11 w-full rounded-md px-3 text-sm md:h-9"
                      placeholder="Team name"
                    />
                    <Input
                      value={teamDescriptionDraft[team.id] ?? ""}
                      onChange={(event) => setTeamDescriptionDraft((prev) => ({ ...prev, [team.id]: event.target.value }))}
                      className="ds-input h-11 w-full rounded-md px-3 text-sm md:h-9"
                      placeholder="Description"
                    />
                  </div>
                  <label className="mb-2 flex items-center gap-2 text-xs">
                    <Checkbox
                      checked={Boolean(teamActiveDraft[team.id])}
                      onCheckedChange={(checked) =>
                        setTeamActiveDraft((prev) => ({
                          ...prev,
                          [team.id]: checked === true,
                        }))
                      }
                    />
                    active
                  </label>

                  <Tabs value={policyMode} onValueChange={(value) => setTeamPolicyModeDraft((prev) => ({ ...prev, [team.id]: value === "advanced" ? "advanced" : "basic" }))}>
                    <TabsList className="h-9">
                      <TabsTrigger value="basic" className="px-3 py-1 text-xs">Basic</TabsTrigger>
                      <TabsTrigger value="advanced" className="px-3 py-1 text-xs">Advanced JSON</TabsTrigger>
                    </TabsList>

                    <TabsContent value="basic" className="space-y-2">
                      <div className="grid gap-2 md:grid-cols-2">
                        <div className="rounded-md border border-border p-2">
                          <p className="mb-1 text-xs text-muted-foreground">Allowed services</p>
                          <div className="flex flex-wrap gap-3">
                            <label className="flex items-center gap-2 text-sm">
                              <Checkbox
                                checked={(teamPolicyAllowedServicesDraft[team.id] ?? []).includes("notion")}
                                onCheckedChange={(checked) => {
                                  const current = teamPolicyAllowedServicesDraft[team.id] ?? [];
                                  const next = checked ? Array.from(new Set([...current, "notion"])) : current.filter((item) => item !== "notion");
                                  setTeamPolicyAllowedServicesDraft((prev) => ({ ...prev, [team.id]: next }));
                                  syncTeamPolicyJsonFromBasic(
                                    team.id,
                                    next,
                                    teamPolicyDenyToolsDraft[team.id] ?? "",
                                    Boolean(teamPolicyAllowHighRiskDraft[team.id]),
                                    teamPolicyLinearTeamIdsDraft[team.id] ?? ""
                                  );
                                }}
                              />
                              notion
                            </label>
                            <label className="flex items-center gap-2 text-sm">
                              <Checkbox
                                checked={(teamPolicyAllowedServicesDraft[team.id] ?? []).includes("linear")}
                                onCheckedChange={(checked) => {
                                  const current = teamPolicyAllowedServicesDraft[team.id] ?? [];
                                  const next = checked ? Array.from(new Set([...current, "linear"])) : current.filter((item) => item !== "linear");
                                  setTeamPolicyAllowedServicesDraft((prev) => ({ ...prev, [team.id]: next }));
                                  syncTeamPolicyJsonFromBasic(
                                    team.id,
                                    next,
                                    teamPolicyDenyToolsDraft[team.id] ?? "",
                                    Boolean(teamPolicyAllowHighRiskDraft[team.id]),
                                    teamPolicyLinearTeamIdsDraft[team.id] ?? ""
                                  );
                                }}
                              />
                              linear
                            </label>
                          </div>
                        </div>

                        <div className="rounded-md border border-border p-2">
                          <p className="mb-1 text-xs text-muted-foreground">Risk</p>
                          <label className="flex items-center gap-2 text-sm">
                            <Checkbox
                              checked={Boolean(teamPolicyAllowHighRiskDraft[team.id])}
                              onCheckedChange={(checked) => {
                                const next = checked === true;
                                setTeamPolicyAllowHighRiskDraft((prev) => ({ ...prev, [team.id]: next }));
                                syncTeamPolicyJsonFromBasic(
                                  team.id,
                                  teamPolicyAllowedServicesDraft[team.id] ?? [],
                                  teamPolicyDenyToolsDraft[team.id] ?? "",
                                  next,
                                  teamPolicyLinearTeamIdsDraft[team.id] ?? ""
                                );
                              }}
                            />
                            Allow high risk
                          </label>
                        </div>
                      </div>

                      <div className="grid gap-2 md:grid-cols-2">
                        <DropdownMenu>
                          <DropdownMenuTrigger asChild>
                            <Button type="button" variant="outline" className="h-11 justify-between rounded-md px-3 text-sm md:h-9">
                              {toolsDropdownLabel(teamPolicyDenyToolsDraft[team.id] ?? "")}
                              <ChevronsUpDown className="h-4 w-4 opacity-70" />
                            </Button>
                          </DropdownMenuTrigger>
                          <DropdownMenuContent className="w-[340px] max-w-[90vw]" align="start">
                            {toolOptions.length === 0 ? <div className="px-2 py-1 text-xs text-muted-foreground">No tools found.</div> : null}
                            {toolOptions.map((tool, index) => {
                              const checked = csvHasValue(teamPolicyDenyToolsDraft[team.id] ?? "", tool.tool_name);
                              return (
                                <div key={`team-policy-deny-${team.id}-${tool.tool_name}`}>
                                  <DropdownMenuCheckboxItem
                                    checked={checked}
                                    onCheckedChange={(nextChecked) => {
                                      const next = updateCsvSelection(teamPolicyDenyToolsDraft[team.id] ?? "", tool.tool_name, nextChecked === true);
                                      setTeamPolicyDenyToolsDraft((prev) => ({ ...prev, [team.id]: next }));
                                      syncTeamPolicyJsonFromBasic(
                                        team.id,
                                        teamPolicyAllowedServicesDraft[team.id] ?? [],
                                        next,
                                        Boolean(teamPolicyAllowHighRiskDraft[team.id]),
                                        teamPolicyLinearTeamIdsDraft[team.id] ?? ""
                                      );
                                    }}
                                  >
                                    {tool.tool_name} ({tool.service})
                                  </DropdownMenuCheckboxItem>
                                  {index < toolOptions.length - 1 ? <DropdownMenuSeparator /> : null}
                                </div>
                              );
                            })}
                          </DropdownMenuContent>
                        </DropdownMenu>

                        <Input
                          value={teamPolicyLinearTeamIdsDraft[team.id] ?? ""}
                          onChange={(event) => {
                            const next = event.target.value;
                            setTeamPolicyLinearTeamIdsDraft((prev) => ({ ...prev, [team.id]: next }));
                            syncTeamPolicyJsonFromBasic(
                              team.id,
                              teamPolicyAllowedServicesDraft[team.id] ?? [],
                              teamPolicyDenyToolsDraft[team.id] ?? "",
                              Boolean(teamPolicyAllowHighRiskDraft[team.id]),
                              next
                            );
                          }}
                          placeholder="Allowed Linear team IDs CSV (optional)"
                          className="ds-input h-11 w-full rounded-md px-3 text-sm md:h-9"
                        />
                      </div>

                      <div className="rounded-md border border-border p-2">
                        <p className="mb-1 text-xs text-muted-foreground">Policy JSON preview</p>
                        <pre className="max-h-44 overflow-auto rounded bg-muted/60 p-2 text-[11px]">{jsonText(teamPolicyPreview)}</pre>
                      </div>
                    </TabsContent>

                    <TabsContent value="advanced" className="space-y-2">
                      <textarea
                        value={teamPolicyDraft[team.id] ?? "{}"}
                        onChange={(event) => setTeamPolicyDraft((prev) => ({ ...prev, [team.id]: event.target.value }))}
                        className="ds-input min-h-[140px] w-full rounded-md px-3 py-2 text-xs font-mono"
                      />
                      <Button type="button" variant="outline" onClick={() => applyTeamAdvancedToBasic(team.id)} className="h-9 rounded-md px-3 text-xs">
                        Apply JSON to Basic
                      </Button>
                    </TabsContent>
                  </Tabs>

                  <div className="mt-2">
                    <Button
                      type="button"
                      onClick={() => void updateTeam(team.id)}
                      disabled={!canManageTeams || savingTeamId === team.id}
                      className="ds-btn h-11 rounded-md px-3 text-sm disabled:cursor-not-allowed disabled:opacity-60 md:h-9"
                      title={canManageTeams ? "" : "Admin role required"}
                    >
                      {savingTeamId === team.id ? "Saving..." : "Save Team Policy"}
                    </Button>
                  </div>
                </div>
              </TabsContent>
            </Tabs>
          </article>
        );
      })}

      {!loading && visibleTeams.length === 0 ? <p className="text-sm text-muted-foreground">No teams found.</p> : null}
    </section>
  );
}
