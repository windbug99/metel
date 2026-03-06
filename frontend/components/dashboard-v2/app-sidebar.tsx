"use client";

import Link from "next/link";
import { ChevronDown, UserCircle2 } from "lucide-react";

import type { NavItem } from "./nav-model";
import DashboardNavList from "./nav-list";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
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
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="outline" className="w-full justify-between">
              <span className="truncate">Org: {currentOrg === "all" ? "All" : `#${currentOrg}`}</span>
              <ChevronDown className="h-4 w-4 opacity-70" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start" className="w-56">
            {orgIds.length > 1 && !isMemberRole ? (
              <DropdownMenuItem onClick={() => setGlobalQuery({ org: "all" })}>Org: All</DropdownMenuItem>
            ) : null}
            {orgIds.length === 0 ? <DropdownMenuItem disabled>Org: None</DropdownMenuItem> : null}
            {orgIds.map((id) => (
              <DropdownMenuItem key={`org-menu-${id}`} onClick={() => setGlobalQuery({ org: String(id) })}>
                Org: #{id}
              </DropdownMenuItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>
      </SidebarHeader>
      <SidebarContent className="px-2 py-2">
        <nav className="space-y-1">
          <DashboardNavList pathname={pathname} navItems={navItems} buildNavHref={buildNavHref} />
        </nav>
      </SidebarContent>
      <SidebarSeparator />
      <SidebarFooter>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" className="w-full justify-start gap-2">
              <UserCircle2 className="h-4 w-4" />
              Profile
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start" className="w-56">
            <DropdownMenuItem asChild>
              <Link href="/dashboard/profile">Profile settings</Link>
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem
              disabled={signingOut}
              onClick={() => {
                onSignOut();
              }}
            >
              {signingOut ? "Signing out..." : "Sign out"}
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
        <Link href="/dashboard/legacy" className="px-2 text-xs text-sidebar-foreground/70 underline">
          Go to legacy single-page dashboard
        </Link>
      </SidebarFooter>
    </Sidebar>
  );
}
