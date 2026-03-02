# Legacy SQL Migrations

이 디렉토리는 **Phase 1 MCP Gateway baseline에 포함되지 않는 과거 마이그레이션**을 보관합니다.

## 정책

- `docs/sql/legacy/` 하위 SQL은 **신규 환경 초기 세팅 시 실행 대상이 아닙니다**.
- 현재 기준 실행 대상은 `docs/sql/` 루트의 비-legacy 마이그레이션입니다.
- 과거 이력 분석/롤백 참고가 필요한 경우에만 legacy SQL을 확인합니다.

## 현재 baseline (2026-03-02)

- `docs/sql/001_create_users_table.sql`
- `docs/sql/002_create_oauth_tokens_table.sql`
- `docs/sql/011_add_oauth_tokens_granted_scopes.sql`
- `docs/sql/012_add_users_timezone.sql`
- `docs/sql/015_create_api_keys_and_tool_calls_tables.sql`
- `docs/sql/016_add_api_keys_allowed_tools.sql`
