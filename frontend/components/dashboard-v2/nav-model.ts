"use client";

export type PermissionSnapshot = {
  user_id: string;
  role: string;
  org_ids?: number[];
  team_ids?: number[];
  permissions: {
    can_read_admin_ops: boolean;
  };
};

export type NavItem = {
  key: string;
  href?: string;
  label: string;
  visible: boolean;
  section: "organization" | "team" | "user";
};

export type BreadcrumbModel = {
  category: string;
  menu: string;
  submenu: string;
};

export const GLOBAL_QUERY_KEYS = ["scope", "org", "team", "range"] as const;

export const PAGE_QUERY_KEYS: Record<string, string[]> = {
  overview: ["overview_window"],
  profile: ["profile_tab"],
  requests: ["requests_tab"],
  security: ["security_tab"],
  apiKeys: ["keys_status"],
  organizations: ["orgs_tab"],
  teamPolicy: ["team_tab"],
  policySimulator: ["sim_mode"],
  mcpUsage: ["usage_status"],
  mcpGuide: ["guide_tab"],
  integrations: ["integration_status"],
  oauthConnections: ["oauth_state"],
  auditEvents: ["audit_status"],
  auditSettings: ["audit_settings_tab"],
  adminOps: ["ops_tab"],
};

export function currentPageKey(pathname: string): keyof typeof PAGE_QUERY_KEYS {
  if (pathname.startsWith("/dashboard/profile")) {
    return "profile";
  }
  if (pathname.startsWith("/dashboard/requests")) {
    return "requests";
  }
  if (pathname.startsWith("/dashboard/security")) {
    return "security";
  }
  if (pathname.startsWith("/dashboard/access/api-keys")) {
    return "apiKeys";
  }
  if (pathname.startsWith("/dashboard/access/organizations")) {
    return "organizations";
  }
  if (pathname.startsWith("/dashboard/access/team-policy")) {
    return "teamPolicy";
  }
  if (pathname.startsWith("/dashboard/control/policy-simulator")) {
    return "policySimulator";
  }
  if (pathname.startsWith("/dashboard/control/mcp-usage")) {
    return "mcpUsage";
  }
  if (pathname.startsWith("/dashboard/control/mcp-guide")) {
    return "mcpGuide";
  }
  if (pathname.startsWith("/dashboard/integrations/webhooks")) {
    return "integrations";
  }
  if (pathname.startsWith("/dashboard/integrations/oauth")) {
    return "oauthConnections";
  }
  if (pathname.startsWith("/dashboard/control/audit-events")) {
    return "auditEvents";
  }
  if (pathname.startsWith("/dashboard/control/audit-settings")) {
    return "auditSettings";
  }
  if (pathname.startsWith("/dashboard/admin/ops")) {
    return "adminOps";
  }
  return "overview";
}

export function pageTitle(pathname: string): string {
  if (pathname.startsWith("/dashboard/profile")) {
    return "Profile";
  }
  if (pathname.startsWith("/dashboard/requests")) {
    return "My Requests";
  }
  if (pathname.startsWith("/dashboard/security")) {
    return "Security";
  }
  if (pathname.startsWith("/dashboard/access/api-keys")) {
    return "API Keys";
  }
  if (pathname.startsWith("/dashboard/access/organizations")) {
    return "Organizations";
  }
  if (pathname.startsWith("/dashboard/access/team-policy")) {
    return "Team Policy";
  }
  if (pathname.startsWith("/dashboard/control/policy-simulator")) {
    return "Policy Simulator";
  }
  if (pathname.startsWith("/dashboard/control/mcp-usage")) {
    return "MCP Usage";
  }
  if (pathname.startsWith("/dashboard/control/mcp-guide")) {
    return "MCP Guide";
  }
  if (pathname.startsWith("/dashboard/integrations/webhooks")) {
    return "Integrations";
  }
  if (pathname.startsWith("/dashboard/integrations/oauth")) {
    return "OAuth Connections";
  }
  if (pathname.startsWith("/dashboard/control/audit-events")) {
    return "Audit Events";
  }
  if (pathname.startsWith("/dashboard/control/audit-settings")) {
    return "Audit Settings";
  }
  if (pathname.startsWith("/dashboard/admin/ops")) {
    return "Admin / Ops";
  }
  return "Overview";
}

export function buildBreadcrumb(pathname: string, scope: "org" | "team" | "user"): BreadcrumbModel {
  const category = scope === "org" ? "Organization" : scope === "team" ? "Team" : "User";

  let menu = "Overview";
  if (pathname.startsWith("/dashboard/access/")) {
    menu = "Access";
  } else if (pathname.startsWith("/dashboard/integrations/")) {
    menu = "Integrations";
  } else if (pathname.startsWith("/dashboard/control/audit")) {
    menu = "Audit";
  } else if (pathname.startsWith("/dashboard/control/")) {
    menu = "Control";
  } else if (pathname.startsWith("/dashboard/profile")) {
    menu = "Profile";
  } else if (pathname.startsWith("/dashboard/requests")) {
    menu = "Requests";
  } else if (pathname.startsWith("/dashboard/security")) {
    menu = "Security";
  } else if (pathname.startsWith("/dashboard/admin/")) {
    menu = "Admin";
  }

  const submenu =
    pathname.startsWith("/dashboard/integrations/oauth") && scope !== "user"
      ? "OAuth Governance"
      : pageTitle(pathname);

  return {
    category,
    menu,
    submenu,
  };
}

export function buildNavItems(permissionSnapshot: PermissionSnapshot | null): NavItem[] {
  const role = String(permissionSnapshot?.role ?? "").toLowerCase();
  const isOwner = role === "owner";
  const isAdmin = role === "admin";
  const isAdminPlus = isOwner || isAdmin;
  const canReadAdminOps = Boolean(permissionSnapshot?.permissions?.can_read_admin_ops);
  return [
    { key: "org-access", href: "/dashboard/access/organizations", label: "Access", visible: isAdminPlus, section: "organization" },
    { key: "org-integrations", href: "/dashboard/integrations/webhooks", label: "Integrations", visible: isAdminPlus, section: "organization" },
    { key: "org-oauth-governance", href: "/dashboard/integrations/oauth", label: "OAuth Governance", visible: isAdminPlus, section: "organization" },
    { key: "org-audit-settings", href: "/dashboard/control/audit-settings", label: "Audit Settings", visible: isAdminPlus, section: "organization" },
    { key: "org-admin-ops", href: "/dashboard/admin/ops", label: "Admin / Ops", visible: canReadAdminOps, section: "organization" },

    { key: "team-overview", href: "/dashboard/overview", label: "Overview", visible: true, section: "team" },
    { key: "team-usage", href: "/dashboard/control/mcp-usage", label: "Usage", visible: true, section: "team" },
    { key: "team-policy", href: "/dashboard/access/team-policy", label: "Team Policy", visible: true, section: "team" },
    { key: "team-agent-guide", href: "/dashboard/control/mcp-guide", label: "Agent Guide", visible: true, section: "team" },
    { key: "team-api-keys", href: "/dashboard/access/api-keys", label: "API Keys", visible: true, section: "team" },
    { key: "team-policy-simulator", href: "/dashboard/control/policy-simulator", label: "Policy Simulator", visible: true, section: "team" },
    { key: "team-audit-events", href: "/dashboard/control/audit-events", label: "Audit Events", visible: true, section: "team" },

    { key: "user-profile", href: "/dashboard/profile", label: "Profile", visible: true, section: "user" },
    { key: "user-my-requests", href: "/dashboard/requests", label: "My Requests", visible: true, section: "user" },
    { key: "user-security", href: "/dashboard/security", label: "Security", visible: true, section: "user" },
    { key: "user-oauth-connections", href: "/dashboard/integrations/oauth", label: "OAuth Connections", visible: true, section: "user" },
  ];
}
