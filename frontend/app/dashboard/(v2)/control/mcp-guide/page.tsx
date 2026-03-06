"use client";

import { Button } from "@/components/ui/button";
import { useMemo, useState } from "react";

function buildExamples(apiBaseUrl: string) {
  const base = apiBaseUrl || "$NEXT_PUBLIC_API_BASE_URL";
  return {
    listTools: `curl -sS "${base}/mcp" \\
  -H "Authorization: Bearer metel_xxx" \\
  -H "Content-Type: application/json" \\
  -d '{"jsonrpc":"2.0","id":"1","method":"list_tools","params":{}}'`,
    callTool: `curl -sS "${base}/mcp" \\
  -H "Authorization: Bearer metel_xxx" \\
  -H "Content-Type: application/json" \\
  -d '{"jsonrpc":"2.0","id":"2","method":"call_tool","params":{"name":"linear_list_issues","arguments":{"first":3}}}'`,
  };
}

export default function DashboardMcpGuidePage() {
  const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";
  const examples = useMemo(() => buildExamples(apiBaseUrl), [apiBaseUrl]);

  const [copyState, setCopyState] = useState<"" | "list_tools" | "call_tool">("");

  const copyText = async (kind: "list_tools" | "call_tool") => {
    const text = kind === "list_tools" ? examples.listTools : examples.callTool;
    try {
      await navigator.clipboard.writeText(text);
      setCopyState(kind);
      window.setTimeout(() => setCopyState(""), 1200);
    } catch {
      setCopyState("");
    }
  };

  return (
    <section className="space-y-4">
      <h1 className="text-2xl font-semibold">MCP Guide</h1>
      <p className="text-sm text-muted-foreground">Quick copy examples for JSON-RPC `list_tools` and `call_tool` usage.</p>

      <article className="ds-card p-4">
        <div className="mb-2 flex items-center justify-between gap-2">
          <p className="text-sm font-medium">1) List tools</p>
          <Button
            type="button"
            onClick={() => void copyText("list_tools")}
            className="ds-btn h-9 rounded-md px-3 text-xs"
          >
            {copyState === "list_tools" ? "Copied" : "Copy"}
          </Button>
        </div>
        <pre className="overflow-x-auto rounded bg-muted/60 p-3 text-[11px] text-muted-foreground">{examples.listTools}</pre>
      </article>

      <article className="ds-card p-4">
        <div className="mb-2 flex items-center justify-between gap-2">
          <p className="text-sm font-medium">2) Call tool</p>
          <Button
            type="button"
            onClick={() => void copyText("call_tool")}
            className="ds-btn h-9 rounded-md px-3 text-xs"
          >
            {copyState === "call_tool" ? "Copied" : "Copy"}
          </Button>
        </div>
        <pre className="overflow-x-auto rounded bg-muted/60 p-3 text-[11px] text-muted-foreground">{examples.callTool}</pre>
      </article>

      <article className="ds-card p-4">
        <p className="text-xs text-muted-foreground">Tip: replace `metel_xxx` with your API key and adjust `tool_name`/`arguments` per connector schema.</p>
      </article>
    </section>
  );
}
