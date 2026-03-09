"use client";

import Link from "next/link";
import {
  Activity,
  Building2,
  FileSearch,
  KeyRound,
  LifeBuoy,
  Link2,
  ListChecks,
  Shield,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  UserRound,
  Users,
  Waypoints,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

import type { NavItem } from "../nav-model";
import { cn } from "@/lib/utils";

type NavMainProps = {
  pathname: string;
  navItems: NavItem[];
  buildNavHref: (targetPath: string, section?: NavItem["section"]) => string;
  collapsed: boolean;
};

export function NavMain({ pathname, navItems, buildNavHref, collapsed }: NavMainProps) {
  const navIconByKey: Record<string, LucideIcon> = {
    "org-access": Building2,
    "org-integrations": Waypoints,
    "org-oauth-governance": Link2,
    "org-audit-settings": ShieldCheck,
    "org-admin-ops": LifeBuoy,
    "team-overview": Sparkles,
    "team-usage": Activity,
    "team-policy": Users,
    "team-agent-guide": SlidersHorizontal,
    "team-api-keys": KeyRound,
    "team-policy-simulator": FileSearch,
    "team-audit-events": ListChecks,
    "user-my-requests": ListChecks,
    "user-security": Shield,
    "user-oauth-connections": UserRound,
  };

  const visibleItems = navItems.filter((item) => item.visible);
  const sectionOrder: Array<{ key: NavItem["section"]; label: string }> = [
    { key: "organization", label: "Organization" },
    { key: "team", label: "Team" },
    { key: "user", label: "User" },
  ];

  return (
    <nav className="space-y-4">
      {sectionOrder.map((section) => {
        const items = visibleItems.filter((item) => item.section === section.key);
        if (items.length === 0) {
          return null;
        }

        return (
          <div key={section.key} className="space-y-0.5">
            {!collapsed ? <p className="px-3 pb-1 text-xs font-light text-sidebar-foreground/70">{section.label}</p> : null}
            <div className={cn(!collapsed && "ml-3 border-l border-sidebar-border pl-3")}>
              {items.map((item) => {
                if (!item.href) {
                  return null;
                }
                const Icon = navIconByKey[item.key] ?? Sparkles;
                const active = pathname.startsWith(item.href);
                return (
                  <Link
                    key={item.key}
                    href={buildNavHref(item.href, item.section)}
                    className={cn(
                      "mb-0.5 flex items-center gap-2 rounded-md px-3 pt-[6px] pb-[6px] text-sm font-light transition-colors",
                      active ? "bg-sidebar-accent text-sidebar-accent-foreground" : "text-sidebar-foreground hover:bg-sidebar-accent/70",
                      collapsed && "mx-auto h-8 w-8 justify-center p-0"
                    )}
                    title={collapsed ? `${section.label}: ${item.label}` : undefined}
                  >
                    <span
                      className={cn(
                        "flex shrink-0 items-center justify-center rounded-sm border border-sidebar-border/60 bg-sidebar-accent/30",
                        collapsed ? "h-8 w-8 border-0 bg-transparent" : "h-5 w-5"
                      )}
                    >
                      <Icon className="h-3.5 w-3.5 shrink-0" />
                    </span>
                    <span className={cn("truncate", collapsed && "hidden")}>{item.label}</span>
                  </Link>
                );
              })}
            </div>
          </div>
        );
      })}
    </nav>
  );
}
