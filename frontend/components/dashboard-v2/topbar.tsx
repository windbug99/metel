"use client";

import { Breadcrumb, BreadcrumbItem, BreadcrumbList, BreadcrumbPage, BreadcrumbSeparator } from "@/components/ui/breadcrumb";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Separator } from "@/components/ui/separator";
import { SidebarTrigger } from "@/components/ui/sidebar";

type TopbarProps = {
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

export default function DashboardTopbar({
  title,
  globalSearchEnabled,
  currentTeam,
  currentRange,
  teamIds,
  setGlobalQuery,
  triggerRefresh,
  toggleTheme,
  theme,
}: TopbarProps) {
  return (
    <header className="sticky top-0 z-10 border-b border-border bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/70">
      <div className="flex h-16 flex-col justify-center gap-3 px-4 py-3 md:flex-row md:items-center md:justify-between md:px-6 md:py-0">
        <div className="flex items-center gap-2">
          <SidebarTrigger />
          <Separator orientation="vertical" className="mr-2 h-4" />
          <Breadcrumb>
            <BreadcrumbList>
              <BreadcrumbItem>Dashboard</BreadcrumbItem>
              <BreadcrumbSeparator />
              <BreadcrumbItem>
                <BreadcrumbPage>{title}</BreadcrumbPage>
              </BreadcrumbItem>
            </BreadcrumbList>
          </Breadcrumb>
        </div>
        <div className="flex flex-wrap items-center gap-2 md:justify-end">
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
            className="h-11 min-w-[84px] rounded-md border border-input bg-background px-2 text-sm md:h-8 md:text-xs"
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
            className="h-11 min-w-[72px] rounded-md border border-input bg-background px-2 text-sm md:h-8 md:text-xs"
          >
            <option value="24h">24h</option>
            <option value="7d">7d</option>
          </select>
          <Button type="button" variant="outline" onClick={triggerRefresh} className="h-11 px-3 text-sm md:h-8 md:text-xs">
            Refresh
          </Button>
          <Button type="button" variant="outline" onClick={toggleTheme} className="h-11 px-3 text-sm md:h-8 md:text-xs">
            {theme === "dark" ? "Light" : "Dark"}
          </Button>
        </div>
      </div>
      {!globalSearchEnabled ? (
        <p className="border-t border-border px-4 py-2 text-[11px] text-muted-foreground md:px-6">
          Global Search is disabled until backend search API scope is finalized.
        </p>
      ) : null}
    </header>
  );
}
