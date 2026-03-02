-- LEGACY NOTICE (2026-03-02): This migration is retained for historical reference and is not part of the Phase 1 MCP Gateway baseline.

alter table public.pipeline_links
  add column if not exists error_code text,
  add column if not exists compensation_status text default 'not_required';
