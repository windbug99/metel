"use client";

import Link from "next/link";
import { ChevronsUpDown, LogOut, Settings } from "lucide-react";

import { Button } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { cn } from "@/lib/utils";

type NavUserProps = {
  signingOut: boolean;
  onSignOut: () => void;
  collapsed: boolean;
  username: string;
  email: string;
};

export function NavUser({ signingOut, onSignOut, collapsed, username, email }: NavUserProps) {
  return (
    <div>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="ghost" className={cn("h-auto w-full justify-between gap-2 rounded-lg px-2 py-2", collapsed && "justify-center px-0")}>
            {!collapsed ? (
              <div className="grid flex-1 text-left text-sm leading-tight">
                <span className="truncate font-semibold">{username}</span>
                <span className="truncate text-xs text-muted-foreground">{email || "-"}</span>
              </div>
            ) : null}
            <ChevronsUpDown className={cn("h-4 w-4", collapsed && "hidden")} strokeWidth={1.5} />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent
          align="start"
          side="right"
          className="w-56 rounded-lg border-border bg-card/95 text-foreground shadow-md backdrop-blur"
        >
          <DropdownMenuItem asChild className="text-sm font-light">
            <Link href="/dashboard/profile">
              <Settings className="mr-2 h-4 w-4" strokeWidth={1.5} />
              Settings
            </Link>
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem
            className="text-sm font-light"
            disabled={signingOut}
            onClick={() => {
              onSignOut();
            }}
          >
            <LogOut className="mr-2 h-4 w-4" strokeWidth={1.5} />
            {signingOut ? "Signing out..." : "Log out"}
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  );
}
