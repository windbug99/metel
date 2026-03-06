"use client";

import Link from "next/link";

import type { NavItem } from "../nav-model";
import {
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarMenuSub,
  SidebarMenuSubButton,
  SidebarMenuSubItem,
} from "@/components/ui/sidebar";

type NavMainProps = {
  pathname: string;
  navItems: NavItem[];
  buildNavHref: (targetPath: string) => string;
};

export function NavMain({ pathname, navItems, buildNavHref }: NavMainProps) {
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
          <SidebarGroup key={item.key} className="p-0">
            <SidebarGroupContent>
              <SidebarMenu>
                <SidebarMenuItem>
                  <SidebarMenuButton asChild isActive={active} tooltip={item.label}>
                    <Link href={buildNavHref(item.href)}>
                      <span>{item.label}</span>
                    </Link>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              </SidebarMenu>
            </SidebarGroupContent>
          </SidebarGroup>
        );
      })}

      {teamSubItems.length > 0 ? (
        <SidebarGroup className="p-0">
          <SidebarGroupLabel>Team</SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              <SidebarMenuSub>
                {teamSubItems.map((item) => {
                  if (!item.href) {
                    return null;
                  }
                  const active = pathname.startsWith(item.href);
                  return (
                    <SidebarMenuSubItem key={item.key}>
                      <SidebarMenuSubButton asChild isActive={active}>
                        <Link href={buildNavHref(item.href)}>
                          <span>{item.label}</span>
                        </Link>
                      </SidebarMenuSubButton>
                    </SidebarMenuSubItem>
                  );
                })}
              </SidebarMenuSub>
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      ) : null}
    </nav>
  );
}
