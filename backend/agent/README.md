# Agent Folder Guide

This folder contains the LLM agent runtime contract for metel.

## Tool Spec Source of Truth

- `tool_specs/schema.json`: validation schema for service tool specs
- `tool_specs/notion.json`: Notion executable tool spec
- `tool_specs/spotify.json`: Spotify executable tool spec
- `pipeline_dsl_schema.json`: pipeline DAG DSL v1 schema (planning contract)
- `pipeline_error_codes.py`: pipeline-level error code enum and retryability policy

## Planned Runtime Modules

- `planner.py`: build execution plan from user goal + guide context
- `service_resolver.py`: infer target services from user request
- `guide_retriever.py`: load summarized guide snippets from `docs/api_guides`
- `registry.py`: load/validate tool specs and dispatch adapter functions
- `loop.py`: tool-calling loop with verification and retry policy
- `safety.py`: hard limits and guardrails
- `observability.py`: step-level logs and request tracing

## Design Rule

LLM must only call tools declared in `tool_specs/*.json`.
Human-readable API guides are references for planning, not direct execution contracts.
