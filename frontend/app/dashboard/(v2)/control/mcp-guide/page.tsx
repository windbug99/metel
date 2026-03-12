"use client";

import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useMemo, useState } from "react";
import PageTitleWithTooltip from "@/components/dashboard-v2/page-title-with-tooltip";

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
    customAgentNode: `// Example: scripts/custom-agent.mjs
const API_BASE = "${base}";
const API_KEY = process.env.METEL_API_KEY;

async function mcp(method, params = {}) {
  const res = await fetch(\`\${API_BASE}/mcp\`, {
    method: "POST",
    headers: {
      "Authorization": \`Bearer \${API_KEY}\`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      jsonrpc: "2.0",
      id: String(Date.now()),
      method,
      params,
    }),
  });
  return res.json();
}

// 1) list tools
console.log(await mcp("list_tools", {}));

// 2) call tool
console.log(await mcp("call_tool", {
  name: "linear_list_issues",
  arguments: { first: 3 }
}));`,
    claudeDesktopConfig: `{
  "mcpServers": {
    "metel": {
      "command": "python",
      "args": ["/ABS/PATH/TO/metel/backend/scripts/mcp_stdio_bridge.py"],
      "env": {
        "API_BASE_URL": "${base}",
        "API_KEY": "metel_xxx",
        "BRIDGE_DEBUG": "1"
      }
    }
  }
}`,
    claudeDesktopCheck: `cd backend
API_BASE_URL="${base}" \\
API_KEY="metel_xxx" \\
python scripts/check_claude_bridge_tools.py`,
    claudeDesktopArgsHelp: `# Find the absolute path for args[0] in your own local clone
cd /path/to/your/metel
realpath backend/scripts/mcp_stdio_bridge.py

# If realpath is unavailable
cd /path/to/your/metel
pwd

# Append /backend/scripts/mcp_stdio_bridge.py to the pwd output
# Example:
# /Users/your-name/workspace/metel/backend/scripts/mcp_stdio_bridge.py`,
    n8nHttpNode: `// n8n HTTP Request node settings
// Method: POST
// URL: ${base}/mcp
// Auth: None (use header)
// Headers:
//   Authorization: Bearer metel_xxx
//   Content-Type: application/json
// Body (JSON):
{
  "jsonrpc": "2.0",
  "id": "n8n-1",
  "method": "list_tools",
  "params": {}
}`,
    n8nCallToolBody: `{
  "jsonrpc": "2.0",
  "id": "n8n-2",
  "method": "call_tool",
  "params": {
    "name": "linear_list_issues",
    "arguments": { "first": 3 }
  }
}`,
    canvaListDesigns: `curl -sS "${base}/mcp" \\
  -H "Authorization: Bearer metel_xxx" \\
  -H "Content-Type: application/json" \\
  -d '{"jsonrpc":"2.0","id":"3","method":"call_tool","params":{"name":"canva_design_list","arguments":{"limit":5,"sort_by":"modified_descending"}}}'`,
    canvaCreateDesign: `curl -sS "${base}/mcp" \\
  -H "Authorization: Bearer metel_xxx" \\
  -H "Content-Type: application/json" \\
  -d '{"jsonrpc":"2.0","id":"4","method":"call_tool","params":{"name":"canva_design_create","arguments":{"title":"Launch Poster","design_type":{"type":"poster","name":"Poster"}}}}'`,
    canvaExportDesign: `curl -sS "${base}/mcp" \\
  -H "Authorization: Bearer metel_xxx" \\
  -H "Content-Type: application/json" \\
  -d '{"jsonrpc":"2.0","id":"5","method":"call_tool","params":{"name":"canva_export_create","arguments":{"design_title":"Launch Poster","format":{"type":"pdf"}}}}'`,
    canvaFolderCreate: `curl -sS "${base}/mcp" \\
  -H "Authorization: Bearer metel_xxx" \\
  -H "Content-Type: application/json" \\
  -d '{"jsonrpc":"2.0","id":"6","method":"call_tool","params":{"name":"canva_folder_create","arguments":{"name":"Campaign Assets","parent_folder_id":"root"}}}'`,
    canvaImportByUrl: `curl -sS "${base}/mcp" \\
  -H "Authorization: Bearer metel_xxx" \\
  -H "Content-Type: application/json" \\
  -d '{"jsonrpc":"2.0","id":"7","method":"call_tool","params":{"name":"canva_url_import_create","arguments":{"title":"Sales Deck","url":"https://cdn.example.com/deck.pdf","mime_type":"application/pdf"}}}'`,
    canvaCommentReply: `curl -sS "${base}/mcp" \\
  -H "Authorization: Bearer metel_xxx" \\
  -H "Content-Type: application/json" \\
  -d '{"jsonrpc":"2.0","id":"8","method":"call_tool","params":{"name":"canva_comment_reply_create","arguments":{"design_id":"DESIGN_ID","thread_id":"THREAD_ID","message_plaintext":"Looks good. Please update slide 4."}}}'`,
    canvaBrandTemplates: `curl -sS "${base}/mcp" \\
  -H "Authorization: Bearer metel_xxx" \\
  -H "Content-Type: application/json" \\
  -d '{"jsonrpc":"2.0","id":"9","method":"call_tool","params":{"name":"canva_brand_templates_list","arguments":{"limit":5,"query":"sales"}}}'`,
  };
}

export default function DashboardMcpGuidePage() {
  const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";
  const examples = useMemo(() => buildExamples(apiBaseUrl), [apiBaseUrl]);

  const [copyState, setCopyState] = useState<
    "" | "list_tools" | "call_tool" | "custom_agent_node" | "claude_config" | "claude_check" | "claude_args_help" | "n8n_http" | "n8n_call" | "canva_list" | "canva_create" | "canva_export" | "canva_folder" | "canva_import" | "canva_comment" | "canva_brand_templates"
  >("");

  const copyText = async (
    kind: "list_tools" | "call_tool" | "custom_agent_node" | "claude_config" | "claude_check" | "claude_args_help" | "n8n_http" | "n8n_call" | "canva_list" | "canva_create" | "canva_export" | "canva_folder" | "canva_import" | "canva_comment" | "canva_brand_templates"
  ) => {
    const text =
      kind === "list_tools"
        ? examples.listTools
        : kind === "call_tool"
          ? examples.callTool
          : kind === "custom_agent_node"
            ? examples.customAgentNode
            : kind === "claude_config"
              ? examples.claudeDesktopConfig
              : kind === "claude_check"
                ? examples.claudeDesktopCheck
                : kind === "claude_args_help"
                  ? examples.claudeDesktopArgsHelp
                  : kind === "n8n_http"
                  ? examples.n8nHttpNode
                  : kind === "n8n_call"
                    ? examples.n8nCallToolBody
                    : kind === "canva_list"
                      ? examples.canvaListDesigns
                      : kind === "canva_create"
                        ? examples.canvaCreateDesign
                        : kind === "canva_export"
                          ? examples.canvaExportDesign
                          : kind === "canva_folder"
                            ? examples.canvaFolderCreate
                            : kind === "canva_import"
                              ? examples.canvaImportByUrl
                              : kind === "canva_comment"
                                ? examples.canvaCommentReply
                                : examples.canvaBrandTemplates;
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
      <PageTitleWithTooltip
        title="Agent Guide"
        tooltip="Connect metel with custom agents, Claude Desktop, or n8n, then run MCP list_tools and call_tool."
      />
      <p className="text-sm text-muted-foreground">Choose one method: `Custom Agent`, `Claude Desktop`, or `n8n`.</p>

      <Tabs defaultValue="custom-agent" className="space-y-4">
        <TabsList className="h-auto w-full justify-start gap-2 p-1">
          <TabsTrigger value="custom-agent" className="h-9 rounded-md px-3 text-sm">
            Custom Agent
          </TabsTrigger>
          <TabsTrigger value="claude-desktop" className="h-9 rounded-md px-3 text-sm">
            Claude Desktop
          </TabsTrigger>
          <TabsTrigger value="n8n" className="h-9 rounded-md px-3 text-sm">
            n8n
          </TabsTrigger>
        </TabsList>

        <TabsContent value="custom-agent">
          <article className="ds-card p-4">
            <p className="mb-2 text-sm font-medium">Method A) Custom Agent integration</p>
            <p className="text-xs text-muted-foreground">
              Add MCP HTTP calls in your own agent runtime code (for example `scripts/custom-agent.mjs`, `agent/runner.py`,
              `server/tools.ts`). Do not add `list_tools`/`call_tool` calls inside dashboard UI files.
            </p>
            <div className="mt-3 mb-2 flex items-center justify-between gap-2">
              <p className="text-xs font-medium">Node.js sample (where to place list_tools / call_tool)</p>
              <Button
                type="button"
                onClick={() => void copyText("custom_agent_node")}
                className="ds-btn h-8 rounded-md px-3 text-xs"
              >
                {copyState === "custom_agent_node" ? "Copied" : "Copy"}
              </Button>
            </div>
            <pre className="overflow-x-auto rounded bg-muted/60 p-3 text-[11px] text-muted-foreground">{examples.customAgentNode}</pre>
          </article>
        </TabsContent>

        <TabsContent value="claude-desktop">
          <article className="ds-card p-4">
            <p className="mb-2 text-sm font-medium">Method B) Claude Desktop integration</p>
            <p className="text-xs text-muted-foreground">
              Claude Desktop requires an MCP stdio process. Use `backend/scripts/mcp_stdio_bridge.py` and register it in Claude config.
            </p>
            <div className="mt-3 mb-2 flex items-center justify-between gap-2">
              <p className="text-xs font-medium">claude_desktop_config.json snippet</p>
              <Button
                type="button"
                onClick={() => void copyText("claude_config")}
                className="ds-btn h-8 rounded-md px-3 text-xs"
              >
                {copyState === "claude_config" ? "Copied" : "Copy"}
              </Button>
            </div>
            <pre className="overflow-x-auto rounded bg-muted/60 p-3 text-[11px] text-muted-foreground">{examples.claudeDesktopConfig}</pre>

            <div className="mt-3 mb-2 flex items-center justify-between gap-2">
              <p className="text-xs font-medium">How to find your own args path</p>
              <Button
                type="button"
                onClick={() => void copyText("claude_args_help")}
                className="ds-btn h-8 rounded-md px-3 text-xs"
              >
                {copyState === "claude_args_help" ? "Copied" : "Copy"}
              </Button>
            </div>
            <pre className="overflow-x-auto rounded bg-muted/60 p-3 text-[11px] text-muted-foreground">{examples.claudeDesktopArgsHelp}</pre>

            <div className="mt-3 mb-2 flex items-center justify-between gap-2">
              <p className="text-xs font-medium">Bridge quick check command</p>
              <Button
                type="button"
                onClick={() => void copyText("claude_check")}
                className="ds-btn h-8 rounded-md px-3 text-xs"
              >
                {copyState === "claude_check" ? "Copied" : "Copy"}
              </Button>
            </div>
            <pre className="overflow-x-auto rounded bg-muted/60 p-3 text-[11px] text-muted-foreground">{examples.claudeDesktopCheck}</pre>
          </article>
        </TabsContent>

        <TabsContent value="n8n">
          <article className="ds-card p-4">
            <p className="mb-2 text-sm font-medium">Method C) n8n workflow integration</p>
            <p className="text-xs text-muted-foreground">
              Use n8n `HTTP Request` node to call metel MCP endpoint. This is recommended for no-code scheduled automation and alert flows.
            </p>
            <div className="mt-3 mb-2 flex items-center justify-between gap-2">
              <p className="text-xs font-medium">n8n HTTP Request node (list_tools)</p>
              <Button
                type="button"
                onClick={() => void copyText("n8n_http")}
                className="ds-btn h-8 rounded-md px-3 text-xs"
              >
                {copyState === "n8n_http" ? "Copied" : "Copy"}
              </Button>
            </div>
            <pre className="overflow-x-auto rounded bg-muted/60 p-3 text-[11px] text-muted-foreground">{examples.n8nHttpNode}</pre>

            <div className="mt-3 mb-2 flex items-center justify-between gap-2">
              <p className="text-xs font-medium">n8n body example (call_tool)</p>
              <Button
                type="button"
                onClick={() => void copyText("n8n_call")}
                className="ds-btn h-8 rounded-md px-3 text-xs"
              >
                {copyState === "n8n_call" ? "Copied" : "Copy"}
              </Button>
            </div>
            <pre className="overflow-x-auto rounded bg-muted/60 p-3 text-[11px] text-muted-foreground">{examples.n8nCallToolBody}</pre>
          </article>
        </TabsContent>
      </Tabs>

      <article className="ds-card p-4">
        <div className="mb-2 flex items-center justify-between gap-2">
          <p className="text-sm font-medium">Common MCP call: 1) list_tools</p>
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
          <p className="text-sm font-medium">Common MCP call: 2) call_tool</p>
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

      <article className="ds-card space-y-4 p-4">
        <p className="text-sm font-medium">Canva MCP examples</p>

        <div>
          <div className="mb-2 flex items-center justify-between gap-2">
            <p className="text-xs font-medium">List recent Canva designs</p>
            <Button type="button" onClick={() => void copyText("canva_list")} className="ds-btn h-8 rounded-md px-3 text-xs">
              {copyState === "canva_list" ? "Copied" : "Copy"}
            </Button>
          </div>
          <pre className="overflow-x-auto rounded bg-muted/60 p-3 text-[11px] text-muted-foreground">{examples.canvaListDesigns}</pre>
        </div>

        <div>
          <div className="mb-2 flex items-center justify-between gap-2">
            <p className="text-xs font-medium">Create Canva design</p>
            <Button type="button" onClick={() => void copyText("canva_create")} className="ds-btn h-8 rounded-md px-3 text-xs">
              {copyState === "canva_create" ? "Copied" : "Copy"}
            </Button>
          </div>
          <pre className="overflow-x-auto rounded bg-muted/60 p-3 text-[11px] text-muted-foreground">{examples.canvaCreateDesign}</pre>
        </div>

        <div>
          <div className="mb-2 flex items-center justify-between gap-2">
            <p className="text-xs font-medium">Export Canva design by title</p>
            <Button type="button" onClick={() => void copyText("canva_export")} className="ds-btn h-8 rounded-md px-3 text-xs">
              {copyState === "canva_export" ? "Copied" : "Copy"}
            </Button>
          </div>
          <pre className="overflow-x-auto rounded bg-muted/60 p-3 text-[11px] text-muted-foreground">{examples.canvaExportDesign}</pre>
        </div>

        <div>
          <div className="mb-2 flex items-center justify-between gap-2">
            <p className="text-xs font-medium">Create Canva folder</p>
            <Button type="button" onClick={() => void copyText("canva_folder")} className="ds-btn h-8 rounded-md px-3 text-xs">
              {copyState === "canva_folder" ? "Copied" : "Copy"}
            </Button>
          </div>
          <pre className="overflow-x-auto rounded bg-muted/60 p-3 text-[11px] text-muted-foreground">{examples.canvaFolderCreate}</pre>
        </div>

        <div>
          <div className="mb-2 flex items-center justify-between gap-2">
            <p className="text-xs font-medium">Import public file into Canva</p>
            <Button type="button" onClick={() => void copyText("canva_import")} className="ds-btn h-8 rounded-md px-3 text-xs">
              {copyState === "canva_import" ? "Copied" : "Copy"}
            </Button>
          </div>
          <pre className="overflow-x-auto rounded bg-muted/60 p-3 text-[11px] text-muted-foreground">{examples.canvaImportByUrl}</pre>
        </div>

        <div>
          <div className="mb-2 flex items-center justify-between gap-2">
            <p className="text-xs font-medium">Reply to Canva comment thread</p>
            <Button type="button" onClick={() => void copyText("canva_comment")} className="ds-btn h-8 rounded-md px-3 text-xs">
              {copyState === "canva_comment" ? "Copied" : "Copy"}
            </Button>
          </div>
          <pre className="overflow-x-auto rounded bg-muted/60 p-3 text-[11px] text-muted-foreground">{examples.canvaCommentReply}</pre>
        </div>

        <div>
          <div className="mb-2 flex items-center justify-between gap-2">
            <p className="text-xs font-medium">List Canva brand templates</p>
            <Button type="button" onClick={() => void copyText("canva_brand_templates")} className="ds-btn h-8 rounded-md px-3 text-xs">
              {copyState === "canva_brand_templates" ? "Copied" : "Copy"}
            </Button>
          </div>
          <pre className="overflow-x-auto rounded bg-muted/60 p-3 text-[11px] text-muted-foreground">{examples.canvaBrandTemplates}</pre>
        </div>
      </article>

      <article className="ds-card p-4">
        <p className="text-sm font-medium">Canva parity note</p>
        <p className="mt-2 text-xs text-muted-foreground">
          metel currently exposes the Canva tools that map to the public Canva Connect API. Claude-style items such as AI design generation,
          structured AI generation, presentation outline review, shortlink resolution, presenter notes, editing-session lifecycle, and merge
          flows are not exposed here because matching public Connect endpoints have not been verified.
        </p>
      </article>

      <article className="ds-card p-4">
        <p className="text-xs text-muted-foreground">
          Tip: replace `metel_xxx` with your API key and adjust `tool_name`/`arguments` per connector schema.
          If no tools appear, verify OAuth connections and API key `allowed_tools`.
        </p>
      </article>
    </section>
  );
}
