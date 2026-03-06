"use client";

import Link from "next/link";
import { CircleUserRound } from "lucide-react";

import { Button } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";

type NavUserProps = {
  signingOut: boolean;
  onSignOut: () => void;
};

export function NavUser({ signingOut, onSignOut }: NavUserProps) {
  return (
    <div className="space-y-1">
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="ghost" className="w-full justify-start gap-2">
            <CircleUserRound className="h-4 w-4" />
            Profile
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start" className="w-56">
          <DropdownMenuItem asChild>
            <Link href="/dashboard/profile">Profile settings</Link>
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem
            disabled={signingOut}
            onClick={() => {
              onSignOut();
            }}
          >
            {signingOut ? "Signing out..." : "Sign out"}
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
      <Link href="/dashboard/legacy" className="block px-2 text-xs text-muted-foreground underline">
        Go to legacy single-page dashboard
      </Link>
    </div>
  );
}
