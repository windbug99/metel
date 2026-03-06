"use client";

type DecisionStatus = "allowed" | "policy_blocked" | "access_denied" | "failed";
type KeyStatus = "active" | "revoked";

type StatusBadgeProps =
  | {
      kind: "decision";
      value: DecisionStatus | string | null | undefined;
    }
  | {
      kind: "key";
      value: KeyStatus | string | null | undefined;
    };

function labelFor(kind: StatusBadgeProps["kind"], value: string | null | undefined): string {
  if (!value) {
    return "-";
  }
  if (kind === "decision") {
    return value;
  }
  if (value === "active") {
    return "active";
  }
  if (value === "revoked") {
    return "revoked";
  }
  return value;
}

function toneClass(kind: StatusBadgeProps["kind"], value: string | null | undefined): string {
  if (!value) {
    return "border-border text-muted-foreground bg-muted";
  }

  if (kind === "decision") {
    if (value === "allowed") {
      return "border-chart-2/35 text-chart-2 bg-chart-2/10";
    }
    if (value === "policy_blocked") {
      return "border-chart-4/35 text-chart-4 bg-chart-4/10";
    }
    if (value === "access_denied" || value === "failed") {
      return "border-destructive/35 text-destructive bg-destructive/10";
    }
    return "border-border text-muted-foreground bg-muted";
  }

  if (value === "active") {
    return "border-chart-2/35 text-chart-2 bg-chart-2/10";
  }
  if (value === "revoked") {
    return "border-destructive/35 text-destructive bg-destructive/10";
  }
  return "border-border text-muted-foreground bg-muted";
}

export default function StatusBadge(props: StatusBadgeProps) {
  const value = props.value ?? null;
  return <span className={`ds-badge ${toneClass(props.kind, value)}`}>{labelFor(props.kind, value)}</span>;
}
