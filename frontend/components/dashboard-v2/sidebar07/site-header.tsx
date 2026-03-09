"use client";

import { Select } from "@/components/ui/select";
import { PanelLeft } from "lucide-react";

import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from "@/components/ui/breadcrumb";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Separator } from "@/components/ui/separator";

type SiteHeaderProps = {
  title: string;
  breadcrumb: {
    menu: string;
    page: string;
  };
  globalSearchEnabled: boolean;
  currentTeam: string;
  currentRange: string;
  currentScope: "org" | "team" | "user";
  currentOrg: string;
  teamIds: number[];
  setGlobalQuery: (next: Partial<Record<"scope" | "org" | "team" | "range", string>>) => void;
  triggerRefresh: () => void;
  onToggleSidebar: () => void;
};

export function SiteHeader({
  title,
  breadcrumb,
  globalSearchEnabled,
  currentTeam,
  currentRange,
  currentScope,
  currentOrg,
  teamIds,
  setGlobalQuery,
  triggerRefresh,
  onToggleSidebar,
}: SiteHeaderProps) {
  return (
    <header className="flex h-16 shrink-0 items-center justify-between gap-2 border-b border-border bg-background px-4 md:px-6">
      <div className="flex min-w-0 items-center gap-2">
        <Button type="button" variant="ghost" size="icon" className="-ml-1 h-8 w-8" onClick={onToggleSidebar}>
          <PanelLeft className="h-4 w-4" />
          <span className="sr-only">Toggle Sidebar</span>
        </Button>
        <Separator orientation="vertical" className="mr-2 data-[orientation=vertical]:h-4" />
        <Breadcrumb>
          <BreadcrumbList>
            <BreadcrumbItem>
              <BreadcrumbPage>{breadcrumb.menu}</BreadcrumbPage>
            </BreadcrumbItem>
            <BreadcrumbSeparator />
            <BreadcrumbItem className="hidden md:block">
              <BreadcrumbPage>{breadcrumb.page || title}</BreadcrumbPage>
            </BreadcrumbItem>
          </BreadcrumbList>
        </Breadcrumb>
      </div>

      <div className="flex items-center justify-end gap-2 md:flex-nowrap">
        <Input
          type="search"
          disabled={!globalSearchEnabled}
          placeholder={
            globalSearchEnabled ? "Search request_id / api_key / user_id / tool_name" : "Global search (coming soon)"
          }
          className="hidden h-8 w-64 text-xs md:block"
        />
        <Select
          value={currentTeam}
          onChange={(event) => {
            const value = event.target.value;
            if (value === "all") {
              if (currentScope === "team") {
                if (currentOrg !== "all") {
                  setGlobalQuery({ scope: "org", team: "all" });
                } else {
                  setGlobalQuery({ scope: "user", team: "all", org: "all" });
                }
                return;
              }
              setGlobalQuery({ team: "all" });
              return;
            }
            if (currentOrg !== "all") {
              setGlobalQuery({ scope: "team", team: value });
            }
          }}
          className="h-8 w-auto min-w-[84px] shrink-0 rounded-md border border-input bg-background px-2 text-xs"
        >
          <option value="all">{teamIds.length === 0 ? "Team: None" : "Team: All"}</option>
          {teamIds.map((id) => (
            <option key={`team-${id}`} value={String(id)}>
              Team: #{id}
            </option>
          ))}
        </Select>
        <Select
          value={currentRange}
          onChange={(event) => setGlobalQuery({ range: event.target.value })}
          className="h-8 w-auto min-w-[72px] shrink-0 rounded-md border border-input bg-background px-2 text-xs"
        >
          <option value="24h">24h</option>
          <option value="7d">7d</option>
        </Select>
        <Button type="button" variant="outline" onClick={triggerRefresh} className="h-8 px-3 text-xs">
          Refresh
        </Button>
      </div>
    </header>
  );
}
