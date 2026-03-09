"use client";

import { Button } from "@/components/ui/button";
type AlertBannerProps = {
  message: string;
  tone?: "info" | "warning" | "danger";
  dismissible?: boolean;
  onDismiss?: () => void;
};

export default function AlertBanner({ message, tone = "warning", dismissible = false, onDismiss }: AlertBannerProps) {
  const classes = tone === "danger"
    ? "border-destructive/40 bg-destructive/10 text-destructive"
    : tone === "info"
      ? "border-primary/40 bg-primary/10 text-primary"
      : "border-chart-4/40 bg-chart-4/10 text-chart-4";

  return (
    <div className={`mb-4 rounded-md border px-3 py-2 text-sm ${classes}`}>
      <div className="flex items-center justify-between gap-2">
        <p>{message}</p>
        {dismissible ? (
          <Button
            type="button"
            onClick={onDismiss}
            className="rounded border border-current px-2 py-1 text-xs"
          >
            Dismiss
          </Button>
        ) : null}
      </div>
    </div>
  );
}
