"use client";

import { supabase } from "./supabase";

export type DashboardApiResult<T> = {
  ok: boolean;
  status: number;
  data?: T;
  error?: string;
};

type DashboardApiRequestOptions = {
  method?: "GET" | "POST" | "PATCH" | "DELETE";
  body?: unknown;
};

export function buildNextPath(pathname: string, search: string): string {
  return search ? `${pathname}${search}` : pathname;
}

export async function dashboardApiRequest<T>(path: string, options: DashboardApiRequestOptions = {}): Promise<DashboardApiResult<T>> {
  const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL;
  if (!apiBaseUrl) {
    return { ok: false, status: 0, error: "NEXT_PUBLIC_API_BASE_URL is not configured." };
  }

  const {
    data: { session },
  } = await supabase.auth.getSession();
  const accessToken = session?.access_token;
  if (!accessToken) {
    return { ok: false, status: 401, error: "No active login session was found." };
  }

  try {
    const method = options.method ?? "GET";
    const headers: HeadersInit = { Authorization: `Bearer ${accessToken}` };
    let body: string | undefined;
    if (options.body !== undefined) {
      headers["Content-Type"] = "application/json";
      body = JSON.stringify(options.body);
    }

    const response = await fetch(`${apiBaseUrl}${path}`, {
      method,
      headers,
      body,
    });

    if (!response.ok) {
      let detailMessage = "";
      try {
        const contentType = response.headers.get("content-type") ?? "";
        if (contentType.includes("application/json")) {
          const errorPayload = (await response.json()) as { detail?: string; message?: string };
          detailMessage = String(errorPayload?.detail ?? errorPayload?.message ?? "").trim();
        }
      } catch {
        // ignore parse failure and fallback to status message
      }
      return {
        ok: false,
        status: response.status,
        error: detailMessage || `Request failed with status ${response.status}`,
      };
    }

    const contentType = response.headers.get("content-type") ?? "";
    if (!contentType.includes("application/json")) {
      return { ok: true, status: response.status };
    }
    const payload = (await response.json()) as T;
    return { ok: true, status: response.status, data: payload };
  } catch {
    return { ok: false, status: 0, error: "Network error while loading dashboard data." };
  }
}

export async function dashboardApiGet<T>(path: string): Promise<DashboardApiResult<T>> {
  return dashboardApiRequest<T>(path, { method: "GET" });
}
