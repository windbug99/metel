"use client";

import Link from "next/link";

import type { NavItem } from "../nav-model";
import { cn } from "@/lib/utils";

type NavMainProps = {
  pathname: string;
  navItems: NavItem[];
  buildNavHref: (targetPath: string, section?: NavItem["section"]) => string;
  collapsed: boolean;
};

export function NavMain({ pathname, navItems, buildNavHref, collapsed }: NavMainProps) {
  const visibleItems = navItems.filter((item) => item.visible);
  const sectionOrder: Array<{ key: NavItem["section"]; label: string }> = [
    { key: "organization", label: "Organization" },
    { key: "team", label: "Team" },
    { key: "user", label: "User" },
  ];

  return (
    <nav className="space-y-1.5">
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
                const active = pathname.startsWith(item.href);
                return (
                  <Link
                    key={item.key}
                    href={buildNavHref(item.href, item.section)}
                    className={cn(
                      "mb-0.5 block rounded-md px-3 pt-[4px] pb-[4px] text-sm font-light transition-colors",
                      active ? "bg-sidebar-accent text-sidebar-accent-foreground" : "text-sidebar-foreground hover:bg-sidebar-accent/70",
                      collapsed && "px-2 text-center"
                    )}
                    title={collapsed ? `${section.label}: ${item.label}` : undefined}
                  >
                    <span className={cn("truncate", collapsed && "hidden")}>{item.label}</span>
                    <span className={cn("hidden", collapsed && "inline")}>{item.label.slice(0, 1)}</span>
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
