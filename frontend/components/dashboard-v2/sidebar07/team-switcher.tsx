"use client";

import { AudioWaveform, ChevronsUpDown, Command, GalleryVerticalEnd, Plus } from "lucide-react";

import { Button } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuShortcut, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { cn } from "@/lib/utils";

type TeamSwitcherProps = {
  currentOrg: string;
  orgIds: number[];
  isMemberRole: boolean;
  setGlobalQuery: (next: Partial<Record<"scope" | "org" | "team" | "range", string>>) => void;
  onAddOrganization: () => void;
  roleLabel: string;
  collapsed: boolean;
};

const ORG_ICONS = [GalleryVerticalEnd, AudioWaveform, Command] as const;

export function TeamSwitcher({
  currentOrg,
  orgIds,
  setGlobalQuery,
  onAddOrganization,
  roleLabel,
  collapsed,
}: TeamSwitcherProps) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="ghost"
          className={cn("h-auto w-full justify-between gap-3 rounded-lg p-2 text-left", collapsed && "justify-center gap-0 px-0")}
        >
          <div className={cn("flex h-8 w-8 items-center justify-center rounded-lg bg-primary text-primary-foreground", collapsed && "h-7 w-7")}>
            <GalleryVerticalEnd className="h-4 w-4" />
          </div>
          <div className={cn("grid flex-1 text-left text-sm leading-tight", collapsed && "hidden")}>
            <span className="truncate font-semibold">{currentOrg === "all" ? "All Organizations" : `Org #${currentOrg}`}</span>
            <span className="truncate text-xs text-muted-foreground">{roleLabel === "loading" ? "loading" : roleLabel}</span>
          </div>
          <ChevronsUpDown className={cn("size-4", collapsed && "hidden")} strokeWidth={1.5} />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent
        align="start"
        side="right"
        className="w-[--radix-dropdown-menu-trigger-width] min-w-56 rounded-lg border-border bg-card/95 text-foreground shadow-md backdrop-blur"
      >
        <DropdownMenuLabel className="text-xs font-light text-muted-foreground">Organizations</DropdownMenuLabel>
        {orgIds.length === 0 ? <DropdownMenuItem className="text-sm font-light" disabled>Org: None</DropdownMenuItem> : null}
        {orgIds.map((id, index) => {
          const Icon = ORG_ICONS[index % ORG_ICONS.length];
          return (
            <DropdownMenuItem key={`org-${id}`} className="gap-2 p-2 text-sm font-light" onClick={() => setGlobalQuery({ scope: "org", org: String(id), team: "all" })}>
              <div className="flex h-6 w-6 items-center justify-center rounded-md border">
                <Icon className="h-3.5 w-3.5" strokeWidth={1.5} />
              </div>
              Org #{id}
              <DropdownMenuShortcut>⌘{index + 1}</DropdownMenuShortcut>
            </DropdownMenuItem>
          );
        })}
        <DropdownMenuSeparator />
        <DropdownMenuItem className="gap-2 p-2 text-sm font-light" onClick={onAddOrganization}>
          <div className="flex h-6 w-6 items-center justify-center rounded-md border">
            <Plus className="h-3.5 w-3.5" strokeWidth={1.5} />
          </div>
          Add organization
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
