"use client";

import Link from "next/link";
import { X } from "lucide-react";
import { BookOpenText } from "lucide-react";

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
  currentOrgName: string | null;
  orgIds: number[];
  orgOptions: Array<{ id: number; name: string }>;
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
  currentOrgName,
  orgIds,
  orgOptions,
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
              currentOrgName={currentOrgName}
              orgIds={orgIds}
              orgOptions={orgOptions}
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

      <div className="flex flex-1 flex-col overflow-hidden">
        <div className="no-scrollbar flex-1 overflow-y-auto px-3 py-3">
          <NavMain pathname={pathname} navItems={navItems} buildNavHref={buildNavHref} collapsed={collapsed} />
        </div>
        <div className="px-3 pb-3">
          <Link
            href={buildNavHref("/dashboard/user-guide", "user")}
            className={cn(
              "flex items-center gap-2 rounded-md border border-sidebar-border px-3 pt-[6px] pb-[6px] text-sm font-light transition-colors",
              pathname.startsWith("/dashboard/user-guide")
                ? "bg-sidebar-accent text-sidebar-accent-foreground"
                : "text-sidebar-foreground hover:bg-sidebar-accent/70",
              collapsed && "mx-auto h-8 w-8 justify-center p-0"
            )}
            title={collapsed ? "User Guide" : undefined}
          >
            <span className={cn("flex shrink-0 items-center justify-center", collapsed ? "h-8 w-8" : "h-5 w-5")}>
              <BookOpenText className="h-3.5 w-3.5 shrink-0" />
            </span>
            <span className={cn("truncate", collapsed && "hidden")}>User Guide</span>
          </Link>
        </div>
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
