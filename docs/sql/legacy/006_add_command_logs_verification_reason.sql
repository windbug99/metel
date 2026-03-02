-- LEGACY NOTICE (2026-03-02): This migration is retained for historical reference and is not part of the Phase 1 MCP Gateway baseline.

alter table public.command_logs
  add column if not exists verification_reason text;