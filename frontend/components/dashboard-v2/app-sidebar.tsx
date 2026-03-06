"use client";

import type { NavItem } from "./nav-model";
import { NavMain } from "./sidebar07/nav-main";
import { NavUser } from "./sidebar07/nav-user";
import { TeamSwitcher } from "./sidebar07/team-switcher";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarHeader,
  SidebarSeparator,
} from "@/components/ui/sidebar";

type AppSidebarProps = {
  pathname: string;
  navItems: NavItem[];
  buildNavHref: (targetPath: string) => string;
  roleLabel: string;
  currentOrg: string;
  orgIds: number[];
  isMemberRole: boolean;
  setGlobalQuery: (next: Partial<Record<"org" | "team" | "range", string>>) => void;
  signingOut: boolean;
  onSignOut: () => void;
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
  signingOut,
  onSignOut,
}: AppSidebarProps) {
  return (
    <Sidebar variant="inset" collapsible="icon">
      <SidebarHeader className="border-b border-sidebar-border">
        <p className="px-2 pt-1 text-sm font-semibold tracking-tight">metel Dashboard</p>
        <p className="px-2 text-[11px] text-sidebar-foreground/70">role: {roleLabel}</p>
        <TeamSwitcher
          currentOrg={currentOrg}
          orgIds={orgIds}
          isMemberRole={isMemberRole}
          setGlobalQuery={setGlobalQuery}
        />
      </SidebarHeader>
      <SidebarContent className="px-2 py-2">
        <NavMain pathname={pathname} navItems={navItems} buildNavHref={buildNavHref} />
      </SidebarContent>
      <SidebarSeparator />
      <SidebarFooter>
        <NavUser signingOut={signingOut} onSignOut={onSignOut} />
      </SidebarFooter>
    </Sidebar>
  );
}
