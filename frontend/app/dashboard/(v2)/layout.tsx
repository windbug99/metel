import { Suspense } from "react";

import DashboardV2Shell from "../../../components/dashboard-v2/shell";

export default function DashboardV2Layout({ children }: { children: React.ReactNode }) {
  return (
    <Suspense fallback={<div className="p-4 text-sm text-muted-foreground">Loading dashboard...</div>}>
      <DashboardV2Shell>{children}</DashboardV2Shell>
    </Suspense>
  );
}
