# Phase 2 Status Snapshot (2026-03-03)

기준 문서:
- `docs/overhaul-20260302.md`
- `docs/work_plan.md`

## 1) 현재 서비스 구조

```text
AI Agent / Client
    -> MCP Gateway (HTTP JSON-RPC)
       -> /mcp/list_tools
       -> /mcp/call_tool
    -> Execution Control Core (Phase 2)
       - API Key Auth / allowed_tools
       - Schema Validation
       - Rate Limit (per-minute)
       - Quota (per-key/per-user daily)
       - Risk Gate
       - Resolver (name -> id)
       - Retry Policy (temporary failure only)
       - Standard Error Codes
       - Usage/Audit Logging (tool_calls)
    -> SaaS APIs (Notion, Linear)
```

## 2) Phase 2까지 구현 완료 기능

### MCP Gateway 기본 기능
- `POST /mcp/list_tools`
- `POST /mcp/call_tool`
- OAuth 연결 상태 + API Key `allowed_tools` 기반 tool 노출/실행 제어

### Safe Execution 기능
- Risk Gate
  - `notion_delete_block` 기본 차단
  - `notion_update_page(archived/in_trash)` 차단
  - `linear_update_issue(archived)` 차단
  - 에러 코드: `policy_blocked`
- Resolver
  - Notion: `page_title/page_name -> page_id`
  - Linear: `team_name -> team_id`
  - 에러 코드: `resolve_not_found`, `resolve_ambiguous`
- Retry
  - 재시도 대상: `RATE_LIMITED`, `status=429/500/502/503/504`
  - 비대상: validation/auth/not_connected/policy 오류
- Quota
  - 일일 사용자/키 단위 쿼터(`MCP_QUOTA_PER_USER_DAILY`, `MCP_QUOTA_PER_KEY_DAILY`)
  - 에러 코드: `quota_exceeded`

### 표준 에러 코드 확장
- `policy_blocked`
- `resolve_not_found`
- `resolve_ambiguous`
- `quota_exceeded`
- `upstream_temporary_failure`

### 운영 가시성
- `/api/tool-calls` summary 확장:
  - `fail_rate_24h`
  - `blocked_rate_24h`
  - `retryable_fail_rate_24h`
  - `policy_blocked_24h`
  - `quota_exceeded_24h`
  - `resolve_fail_24h`
  - `upstream_temporary_24h`
  - `top_failure_codes`
- 대시보드에 위 지표 노출

## 3) 테스트/검증 상태

### 자동 테스트
- Backend:
  - `tests/test_mcp_routes.py`
  - `tests/test_tool_calls_route.py`
- Frontend:
  - `pnpm -s tsc --noEmit`

### 배포 스모크 테스트
- 자동 스크립트:
  - `backend/scripts/run_mcp_smoke.sh`
- 최근 결과(Production, 2026-03-03):
  - `pass=8 fail=0`
  - 검증 항목:
    - list_tools
    - notion_retrieve_bot_user
    - linear_get_viewer
    - structured schema error
    - risk gate policy block

## 4) 현재 상태 결론

- Phase 1(MCP Gateway MVP): 완료
- Phase 2(Safe Execution 강화): 구현/검증 완료
- 현재 제품 상태:
  - "MCP Gateway + Safe Execution Core"가 운영 가능한 테스트버전으로 정착
  - 다음 단계는 Phase 3(Execution Control Platform 전환)

## 5) Phase 3 진입 전 운영 체크

- 테스트용 API Key 전량 revoke 및 운영 키 재발급
- Quota/Retry 운영값 확정(`backend/.env`)
- 배포 후 `run_mcp_smoke.sh`를 배포 게이트로 고정
