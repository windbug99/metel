"use client";

import { ChevronsUpDown } from "lucide-react";

import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { SidebarMenu, SidebarMenuButton, SidebarMenuItem } from "@/components/ui/sidebar";

type TeamSwitcherProps = {
  currentOrg: string;
  orgIds: number[];
  isMemberRole: boolean;
  setGlobalQuery: (next: Partial<Record<"org" | "team" | "range", string>>) => void;
};

export function TeamSwitcher({ currentOrg, orgIds, isMemberRole, setGlobalQuery }: TeamSwitcherProps) {
  return (
    <SidebarMenu>
      <SidebarMenuItem>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <SidebarMenuButton className="justify-between">
              <span className="truncate">Org: {currentOrg === "all" ? "All" : `#${currentOrg}`}</span>
              <ChevronsUpDown className="ml-auto size-4" />
            </SidebarMenuButton>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start" className="w-56 rounded-lg">
            {orgIds.length > 1 && !isMemberRole ? (
              <DropdownMenuItem onClick={() => setGlobalQuery({ org: "all" })}>Org: All</DropdownMenuItem>
            ) : null}
            {orgIds.length === 0 ? <DropdownMenuItem disabled>Org: None</DropdownMenuItem> : null}
            {orgIds.map((id) => (
              <DropdownMenuItem key={`org-${id}`} onClick={() => setGlobalQuery({ org: String(id) })}>
                Org: #{id}
              </DropdownMenuItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>
      </SidebarMenuItem>
    </SidebarMenu>
  );
}
