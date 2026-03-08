"use client";

import { X } from "lucide-react";

import type { NavItem } from "./nav-model";
import { NavMain } from "./sidebar07/nav-main";
import { NavUser } from "./sidebar07/nav-user";
import { TeamSwitcher } from "./sidebar07/team-switcher";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

type AppSidebarProps = {
  pathname: string;
  navItems: NavItem[];
  buildNavHref: (targetPath: string, section?: NavItem["section"]) => string;
  roleLabel: string;
  currentOrg: string;
  orgIds: number[];
  isMemberRole: boolean;
  setGlobalQuery: (next: Partial<Record<"scope" | "org" | "team" | "range", string>>) => void;
  onAddOrganization: () => void;
  signingOut: boolean;
  onSignOut: () => void;
  username: string;
  email: string;
  collapsed: boolean;
  mobileOpen: boolean;
  onCloseMobile: () => void;
};

export default function DashboardAppSidebar({
  pathname,
  navItems,
  buildNavHref,
  roleLabel,
  currentOrg,
  orgIds,
  isMemberRole,
  setGlobalQuery,
  onAddOrganization,
  signingOut,
  onSignOut,
  username,
  email,
  collapsed,
  mobileOpen,
  onCloseMobile,
}: AppSidebarProps) {
  return (
    <aside
      className={cn(
        "fixed inset-y-0 left-0 z-40 flex h-svh w-64 flex-col overflow-hidden border-r border-sidebar-border bg-sidebar text-sidebar-foreground transition-transform md:static md:z-auto md:h-svh md:translate-x-0",
        mobileOpen ? "translate-x-0" : "-translate-x-full",
        collapsed ? "md:w-16" : "md:w-64"
      )}
    >
      <div className="h-16 border-b border-sidebar-border px-2">
        <div className="flex h-full items-center gap-2">
          <div className="min-w-0 flex-1">
            <TeamSwitcher
              currentOrg={currentOrg}
              orgIds={orgIds}
              isMemberRole={isMemberRole}
              setGlobalQuery={setGlobalQuery}
              onAddOrganization={onAddOrganization}
              roleLabel={roleLabel}
              collapsed={collapsed}
            />
          </div>
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="h-8 w-8 md:hidden"
            onClick={onCloseMobile}
            aria-label="Close Sidebar"
          >
            <X className="h-4 w-4" />
          </Button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-3 py-3">
        <NavMain pathname={pathname} navItems={navItems} buildNavHref={buildNavHref} collapsed={collapsed} />
      </div>

      <div className="border-t border-sidebar-border p-3">
        <NavUser
          signingOut={signingOut}
          onSignOut={onSignOut}
          collapsed={collapsed}
          username={username}
          email={email}
        />
      </div>
    </aside>
  );
}
