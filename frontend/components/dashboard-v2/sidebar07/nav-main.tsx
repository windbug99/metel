"use client";

import Link from "next/link";

import type { NavItem } from "../nav-model";
import { cn } from "@/lib/utils";

type NavMainProps = {
  pathname: string;
  navItems: NavItem[];
  buildNavHref: (targetPath: string) => string;
  collapsed: boolean;
};

export function NavMain({ pathname, navItems, buildNavHref, collapsed }: NavMainProps) {
  const visibleItems = navItems.filter((item) => item.visible);
  const topLevelItems = visibleItems.filter((item) => item.depth !== 1 && item.key !== "team");
  const teamSubItems = visibleItems.filter((item) => item.depth === 1);

  return (
    <nav className="space-y-1">
      {topLevelItems.map((item) => {
        if (!item.href) {
          return null;
        }
        const active = pathname.startsWith(item.href);
        return (
          <Link
            key={item.key}
            href={buildNavHref(item.href)}
            className={cn(
              "block rounded-md px-3 py-2 text-sm font-light transition-colors",
              active ? "bg-sidebar-accent text-sidebar-accent-foreground" : "text-sidebar-foreground hover:bg-sidebar-accent/70",
              collapsed && "px-2 text-center"
            )}
            title={collapsed ? item.label : undefined}
          >
            <span className={cn("truncate", collapsed && "hidden")}>{item.label}</span>
            <span className={cn("hidden", collapsed && "inline")}>{item.label.slice(0, 1)}</span>
          </Link>
        );
      })}

      {teamSubItems.length > 0 && !collapsed ? (
        <div className="pt-2">
          <p className="px-3 pb-1 text-xs font-light text-sidebar-foreground/70">Team</p>
          <div className="ml-3 space-y-1 border-l border-sidebar-border pl-3">
            {teamSubItems.map((item) => {
              if (!item.href) {
                return null;
              }
              const active = pathname.startsWith(item.href);
              return (
                <Link
                  key={item.key}
                  href={buildNavHref(item.href)}
                  className={cn(
                    "block rounded-md px-2 py-1.5 text-sm font-light",
                    active ? "bg-sidebar-accent text-sidebar-accent-foreground" : "text-sidebar-foreground hover:bg-sidebar-accent/70"
                  )}
                >
                  {item.label}
                </Link>
              );
            })}
          </div>
        </div>
      ) : null}
    </nav>
  );
}
