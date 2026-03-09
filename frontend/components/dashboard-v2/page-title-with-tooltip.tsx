"use client";

import { Info } from "lucide-react";

import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";

type PageTitleWithTooltipProps = {
  title: string;
  tooltip: string;
};

export default function PageTitleWithTooltip({ title, tooltip }: PageTitleWithTooltipProps) {
  return (
    <div className="flex items-center gap-2">
      <h1 className="text-2xl font-semibold">{title}</h1>
      <TooltipProvider delayDuration={150}>
        <Tooltip>
          <TooltipTrigger asChild>
            <button
              type="button"
              aria-label={`${title} info`}
              className="inline-flex h-6 w-6 items-center justify-center rounded-full border border-border text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground"
            >
              <Info className="h-3.5 w-3.5" />
            </button>
          </TooltipTrigger>
          <TooltipContent>
            <p>{tooltip}</p>
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>
    </div>
  );
}
