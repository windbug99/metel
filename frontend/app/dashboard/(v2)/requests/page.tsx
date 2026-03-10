"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { buildNextPath, dashboardApiGet, dashboardApiRequest } from "../../../../lib/dashboard-v2-client";
import PageTitleWithTooltip from "@/components/dashboard-v2/page-title-with-tooltip";

type RequestType = "permission_request";
type RequestStatus = "pending" | "approved" | "rejected" | "cancelled";

type MyRequestItem = {
  id: number | string;
  organization_id: number;
  organization_name?: string | null;
  request_type: RequestType;
  requested_role: "owner" | "admin" | "member";
  reason?: string | null;
  review_reason?: string | null;
  status: RequestStatus;
  requested_by: string;
  reviewed_by?: string | null;
  reviewed_at?: string | null;
  cancelled_by?: string | null;
  cancelled_at?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
};

type MyRequestsPayload = {
  items: MyRequestItem[];
  count: number;
};

type MyRequestDetailPayload = {
  item: MyRequestItem;
};

type CreateMyRequestPayload = {
  item: MyRequestItem;
};

type OrganizationItem = {
  id: number;
  name: string;
};

type OrganizationsPayload = {
  items: OrganizationItem[];
};

function formatDate(value?: string | null): string {
  if (!value) {
    return "-";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString();
}

function requestTypeLabel(value: RequestType): string {
  return "Permission Request";
}

function statusLabel(value: RequestStatus): string {
  if (value === "approved") {
    return "Approved";
  }
  if (value === "rejected") {
    return "Rejected";
  }
  if (value === "cancelled") {
    return "Cancelled";
  }
  return "Pending";
}

export default function DashboardMyRequestsPage() {
  const pathname = usePathname();
  const router = useRouter();

  const [organizations, setOrganizations] = useState<OrganizationItem[]>([]);
  const [items, setItems] = useState<MyRequestItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [statusFilter, setStatusFilter] = useState<"all" | RequestStatus>("all");
  const [selectedRequestId, setSelectedRequestId] = useState<string | null>(null);
  const [selectedRequest, setSelectedRequest] = useState<MyRequestItem | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);

  const [createOrgId, setCreateOrgId] = useState("");
  const [createRole, setCreateRole] = useState<"owner" | "admin" | "member">("admin");
  const [createReason, setCreateReason] = useState("");
  const [createDialogOpen, setCreateDialogOpen] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);

  const [cancellingId, setCancellingId] = useState<string | null>(null);

  const handle401 = useCallback(() => {
    const next = encodeURIComponent(buildNextPath(pathname, window.location.search));
    router.replace(`/?next=${next}`);
  }, [pathname, router]);

  const loadOrganizations = useCallback(async () => {
    const orgRes = await dashboardApiGet<OrganizationsPayload>("/api/organizations");
    if (orgRes.status === 401) {
      handle401();
      return;
    }
    if (orgRes.ok && Array.isArray(orgRes.data?.items)) {
      const nextItems = orgRes.data.items;
      setOrganizations(nextItems);
      setCreateOrgId((prev) => (prev || nextItems.length === 0 ? prev : String(nextItems[0].id)));
    }
  }, [handle401]);

  const loadRequests = useCallback(async () => {
    setLoading(true);
    setError(null);

    const query = new URLSearchParams();
    if (statusFilter !== "all") {
      query.set("status", statusFilter);
    }
    const suffix = query.toString();

    const response = await dashboardApiGet<MyRequestsPayload>(`/api/users/me/requests${suffix ? `?${suffix}` : ""}`);
    if (response.status === 401) {
      handle401();
      setLoading(false);
      return;
    }
    if (!response.ok || !response.data) {
      setError(response.error ?? "Failed to load request history.");
      setItems([]);
      setLoading(false);
      return;
    }

    const nextItems = Array.isArray(response.data.items) ? response.data.items : [];
    setItems(nextItems);
    if (nextItems.length === 0) {
      setSelectedRequestId(null);
      setSelectedRequest(null);
      setLoading(false);
      return;
    }

    setSelectedRequestId((prev) => {
      if (!prev) {
        return String(nextItems[0].id);
      }
      const selected = nextItems.find((item) => String(item.id) === prev);
      return selected ? prev : String(nextItems[0].id);
    });
    setLoading(false);
  }, [handle401, statusFilter]);

  const loadRequestDetail = useCallback(
    async (requestId: string) => {
      setDetailLoading(true);
      setDetailError(null);
      const response = await dashboardApiGet<MyRequestDetailPayload>(`/api/users/me/requests/${requestId}`);
      if (response.status === 401) {
        handle401();
        setDetailLoading(false);
        return;
      }
      if (!response.ok || !response.data?.item) {
        setDetailError(response.error ?? "Failed to load request detail.");
        setSelectedRequest(null);
        setDetailLoading(false);
        return;
      }
      setSelectedRequest(response.data.item);
      setDetailLoading(false);
    },
    [handle401]
  );

  const handleCreate = useCallback(async () => {
    if (!createOrgId) {
      setCreateError("Organization is required.");
      return;
    }
    setCreating(true);
    setCreateError(null);

    const response = await dashboardApiRequest<CreateMyRequestPayload>("/api/users/me/requests", {
      method: "POST",
      body: {
        organization_id: createOrgId,
        request_type: "permission_request",
        requested_role: createRole,
        reason: createReason.trim() || null,
      },
    });

    if (response.status === 401) {
      handle401();
      setCreating(false);
      return;
    }
    if (!response.ok || !response.data?.item) {
      setCreateError(response.error ?? "Failed to create request.");
      setCreating(false);
      return;
    }

    setCreateReason("");
    setCreateError(null);
    setCreateDialogOpen(false);
    setSelectedRequestId(String(response.data.item.id));
    await loadRequests();
    setCreating(false);
  }, [createOrgId, createRole, createReason, handle401, loadRequests]);

  const handleCancel = useCallback(
    async (requestId: string) => {
      setCancellingId(requestId);
      setError(null);
      const response = await dashboardApiRequest(`/api/users/me/requests/${requestId}/cancel`, {
        method: "POST",
        body: {
          reason: "Cancelled by requester",
        },
      });
      if (response.status === 401) {
        handle401();
        setCancellingId(null);
        return;
      }
      if (!response.ok) {
        setError(response.error ?? "Failed to cancel request.");
        setCancellingId(null);
        return;
      }
      await loadRequests();
      if (selectedRequestId === requestId) {
        await loadRequestDetail(requestId);
      }
      setCancellingId(null);
    },
    [handle401, loadRequestDetail, loadRequests, selectedRequestId]
  );

  const timeline = useMemo(() => {
    if (!selectedRequest) {
      return [] as Array<{ key: string; label: string; at: string }>;
    }
    const rows: Array<{ key: string; label: string; at: string }> = [];
    rows.push({ key: "created", label: "Created", at: formatDate(selectedRequest.created_at) });
    if (selectedRequest.reviewed_at) {
      rows.push({ key: "reviewed", label: `Reviewed (${statusLabel(selectedRequest.status)})`, at: formatDate(selectedRequest.reviewed_at) });
    }
    if (selectedRequest.cancelled_at) {
      rows.push({ key: "cancelled", label: "Cancelled", at: formatDate(selectedRequest.cancelled_at) });
    }
    return rows;
  }, [selectedRequest]);

  useEffect(() => {
    void loadOrganizations();
  }, [loadOrganizations]);

  useEffect(() => {
    void loadRequests();
  }, [loadRequests]);

  useEffect(() => {
    if (selectedRequestId) {
      void loadRequestDetail(selectedRequestId);
    }
  }, [loadRequestDetail, selectedRequestId]);

  if (loading) {
    return (
      <section className="space-y-4">
        <div>
          <PageTitleWithTooltip
            title="My Requests"
            tooltip="Create and track your access and role change requests."
          />
          <p className="text-sm text-muted-foreground">Submit role/access requests and track review status.</p>
        </div>
        <div className="ds-card flex min-h-[220px] items-center justify-center p-4">
          <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
        </div>
      </section>
    );
  }

  return (
    <section className="space-y-4">
      <div>
        <PageTitleWithTooltip
          title="My Requests"
          tooltip="Create and track your access and role change requests."
        />
        <p className="text-sm text-muted-foreground">Submit role/access requests and track review status.</p>
      </div>

      <div className="flex items-center justify-end">
        <Button
          type="button"
          onClick={() => {
            setCreateError(null);
            setCreateDialogOpen(true);
          }}
          disabled={organizations.length === 0}
          className="ds-btn h-10 rounded-md px-3 text-sm disabled:cursor-not-allowed disabled:opacity-60"
        >
          Create Request
        </Button>
      </div>

      <Dialog
        open={createDialogOpen}
        onOpenChange={(open) => {
          if (!creating) {
            setCreateDialogOpen(open);
            if (!open) {
              setCreateError(null);
            }
          }
        }}
      >
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>Create Request</DialogTitle>
            <DialogDescription>Submit a permission request for your current organization membership.</DialogDescription>
          </DialogHeader>
          <div className="space-y-3 py-2">
            {createError ? <p className="text-sm text-destructive">{createError}</p> : null}
            <div className="grid gap-2 md:grid-cols-2">
              <label className="space-y-1">
                <span className="text-xs text-muted-foreground">Organization</span>
                <Select
                  value={createOrgId}
                  onChange={(event) => setCreateOrgId(event.target.value)}
                  className="ds-input h-10 rounded-md px-3 text-sm"
                >
                  {organizations.map((org) => (
                    <option key={org.id} value={String(org.id)}>
                      {org.name}
                    </option>
                  ))}
                </Select>
              </label>

              <label className="space-y-1">
                <span className="text-xs text-muted-foreground">Requested Role</span>
                <Select
                  value={createRole}
                  onChange={(event) => setCreateRole(event.target.value as "owner" | "admin" | "member")}
                  className="ds-input h-10 rounded-md px-3 text-sm"
                >
                  <option value="member">member</option>
                  <option value="admin">admin</option>
                  <option value="owner">owner</option>
                </Select>
              </label>
            </div>

            <label className="space-y-1">
              <span className="text-xs text-muted-foreground">Reason</span>
              <Input
                value={createReason}
                onChange={(event) => setCreateReason(event.target.value)}
                className="ds-input h-10 rounded-md px-3 text-sm"
                placeholder="Describe why this request is needed"
              />
            </label>
          </div>
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => {
                setCreateDialogOpen(false);
                setCreateError(null);
              }}
              disabled={creating}
              className="h-10 rounded-md px-3 text-sm"
            >
              Cancel
            </Button>
            <Button
              type="button"
              onClick={() => void handleCreate()}
              disabled={creating || !createOrgId}
              className="ds-btn h-10 rounded-md px-3 text-sm disabled:cursor-not-allowed disabled:opacity-60"
            >
              {creating ? "Submitting..." : "Submit Request"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {error ? <p className="text-sm text-destructive">{error}</p> : null}

      <div className="ds-card space-y-3 p-4">
        <div className="flex flex-wrap gap-2">
          <Select
            value={statusFilter}
            onChange={(event) => setStatusFilter(event.target.value as "all" | RequestStatus)}
            className="ds-input h-10 w-[170px] rounded-md px-3 text-sm"
          >
            <option value="all">All Statuses</option>
            <option value="pending">Pending</option>
            <option value="approved">Approved</option>
            <option value="rejected">Rejected</option>
            <option value="cancelled">Cancelled</option>
          </Select>
        </div>

        {items.length === 0 ? <p className="text-sm text-muted-foreground">No request history.</p> : null}

        <div className="space-y-2">
          {items.map((item) => {
            const itemId = String(item.id);
            const isSelected = selectedRequestId === itemId;
            const isPending = item.status === "pending";
            const selectedMatches = isSelected && selectedRequest && String(selectedRequest.id) === itemId;

            return (
              <div
                key={itemId}
                className={`rounded-md border p-3 transition-colors ${
                  isSelected ? "border-foreground/30 bg-sidebar-accent/50" : "border-border hover:bg-sidebar-accent/20"
                }`}
              >
                <button
                  type="button"
                  onClick={() => {
                    setSelectedRequestId((prev) => (prev === itemId ? null : itemId));
                  }}
                  className="w-full text-left"
                >
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <p className="text-sm font-medium">
                      {requestTypeLabel(item.request_type)} • {item.organization_name ?? `Org #${item.organization_id}`}
                    </p>
                    <p className="text-xs text-muted-foreground">{statusLabel(item.status)}</p>
                  </div>
                  <p className="mt-1 text-xs text-muted-foreground">Role: {item.requested_role}</p>
                  <p className="mt-1 text-xs text-muted-foreground">Created: {formatDate(item.created_at)}</p>
                </button>

                {isPending ? (
                  <div className="mt-2">
                    <Button
                      type="button"
                      onClick={() => void handleCancel(itemId)}
                      disabled={cancellingId === itemId}
                      className="ds-btn h-8 rounded-md px-2 text-xs disabled:cursor-not-allowed disabled:opacity-60"
                    >
                      {cancellingId === itemId ? "Cancelling..." : "Cancel Request"}
                    </Button>
                  </div>
                ) : null}

                {isSelected ? (
                  <div className="mt-3 space-y-3 border-t border-border pt-3">
                    {detailLoading ? <p className="text-sm text-muted-foreground">Loading detail...</p> : null}
                    {detailError ? <p className="text-sm text-destructive">{detailError}</p> : null}

                    {selectedMatches ? (
                      <div className="space-y-3">
                        <div className="space-y-1">
                          <p className="text-xs text-muted-foreground">Type</p>
                          <p className="text-sm">{requestTypeLabel(selectedRequest.request_type)}</p>
                        </div>
                        <div className="space-y-1">
                          <p className="text-xs text-muted-foreground">Status</p>
                          <p className="text-sm">{statusLabel(selectedRequest.status)}</p>
                        </div>
                        <div className="space-y-1">
                          <p className="text-xs text-muted-foreground">Requested Role</p>
                          <p className="text-sm">{selectedRequest.requested_role}</p>
                        </div>
                        <div className="space-y-1">
                          <p className="text-xs text-muted-foreground">Request Reason</p>
                          <p className="text-sm">{selectedRequest.reason ?? "-"}</p>
                        </div>
                        <div className="space-y-1">
                          <p className="text-xs text-muted-foreground">Review Reason</p>
                          <p className="text-sm">{selectedRequest.review_reason ?? "-"}</p>
                        </div>

                        <div className="space-y-2 border-t border-border pt-3">
                          <p className="text-xs text-muted-foreground">Timeline</p>
                          {timeline.map((entry) => (
                            <div key={entry.key} className="flex items-center justify-between text-xs">
                              <span>{entry.label}</span>
                              <span className="text-muted-foreground">{entry.at}</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    ) : null}
                  </div>
                ) : null}
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}
