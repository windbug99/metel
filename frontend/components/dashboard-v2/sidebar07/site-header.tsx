"use client";

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
import { SidebarTrigger } from "@/components/ui/sidebar";

type SiteHeaderProps = {
  title: string;
  globalSearchEnabled: boolean;
  currentTeam: string;
  currentRange: string;
  teamIds: number[];
  setGlobalQuery: (next: Partial<Record<"org" | "team" | "range", string>>) => void;
  triggerRefresh: () => void;
  toggleTheme: () => void;
  theme: "light" | "dark";
};

export function SiteHeader({
  title,
  globalSearchEnabled,
  currentTeam,
  currentRange,
  teamIds,
  setGlobalQuery,
  triggerRefresh,
  toggleTheme,
  theme,
}: SiteHeaderProps) {
  return (
    <header className="flex h-16 shrink-0 items-center justify-between gap-2 border-b border-border bg-background px-4 transition-[width,height] ease-linear group-has-data-[collapsible=icon]/sidebar-wrapper:h-12 md:px-6">
      <div className="flex min-w-0 items-center gap-2">
        <SidebarTrigger className="-ml-1" />
        <Separator orientation="vertical" className="mr-2 data-[orientation=vertical]:h-4" />
        <Breadcrumb>
          <BreadcrumbList>
            <BreadcrumbItem className="hidden md:block">Dashboard</BreadcrumbItem>
            <BreadcrumbSeparator className="hidden md:block" />
            <BreadcrumbItem>
              <BreadcrumbPage>{title}</BreadcrumbPage>
            </BreadcrumbItem>
          </BreadcrumbList>
        </Breadcrumb>
      </div>

      <div className="flex flex-wrap items-center justify-end gap-2">
        <Input
          type="search"
          disabled={!globalSearchEnabled}
          placeholder={
            globalSearchEnabled ? "Search request_id / api_key / user_id / tool_name" : "Global search (coming soon)"
          }
          className="hidden h-8 w-64 text-xs md:block"
        />
        <select
          value={currentTeam}
          onChange={(event) => setGlobalQuery({ team: event.target.value })}
          className="h-8 min-w-[84px] rounded-md border border-input bg-background px-2 text-xs"
        >
          <option value="all">{teamIds.length === 0 ? "Team: None" : "Team: All"}</option>
          {teamIds.map((id) => (
            <option key={`team-${id}`} value={String(id)}>
              Team: #{id}
            </option>
          ))}
        </select>
        <select
          value={currentRange}
          onChange={(event) => setGlobalQuery({ range: event.target.value })}
          className="h-8 min-w-[72px] rounded-md border border-input bg-background px-2 text-xs"
        >
          <option value="24h">24h</option>
          <option value="7d">7d</option>
        </select>
        <Button type="button" variant="outline" onClick={triggerRefresh} className="h-8 px-3 text-xs">
          Refresh
        </Button>
        <Button type="button" variant="outline" onClick={toggleTheme} className="h-8 px-3 text-xs">
          {theme === "dark" ? "Light" : "Dark"}
        </Button>
      </div>
    </header>
  );
}
