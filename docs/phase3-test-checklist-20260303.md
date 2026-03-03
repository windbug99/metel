# Phase 3 Test Checklist (2026-03-03)

목적:
- Phase 3 (Execution Control Platform) 구현 완료 상태를 기능/정책/운영 관점에서 검증

실행 이력 (2026-03-03):
- `./scripts/run_phase3_full_check.sh` (RUN_MCP_SMOKE=0): PASS
  - phase3 regression: `39 passed`
  - core regression: `58 passed`
  - frontend typecheck: PASS
- `RUN_MCP_SMOKE=1 API_BASE_URL=https://metel-production.up.railway.app API_KEY=*** ./scripts/run_phase3_full_check.sh`: PASS
  - mcp-smoke: `pass=8 fail=0`
- `RUN_MCP_SMOKE=1 RUN_POLICY_SCENARIOS=1 RUN_DASHBOARD_CONSISTENCY=1 API_BASE_URL=https://metel-production.up.railway.app API_KEY=*** USER_JWT=*** ./scripts/run_phase3_full_check.sh`: PASS
  - mcp-smoke: `pass=8 fail=0`
  - policy scenarios: `pass=6 fail=0`
  - dashboard consistency: `pass=11 fail=0`
- `RUN_MCP_SMOKE=1 RUN_POLICY_SCENARIOS=1 RUN_DASHBOARD_CONSISTENCY=1 RUN_STRICT_HIGH_RISK=1 API_BASE_URL=https://metel-production.up.railway.app API_KEY=*** USER_JWT=*** ./scripts/run_phase3_full_check.sh`: PASS
  - mcp-smoke: `pass=8 fail=0`
  - policy scenarios (strict): `pass=7 fail=0`
  - dashboard consistency: `pass=11 fail=0`
- GitHub Actions `backend-phase3-regression`: PASS
  - workflow_dispatch run: `22613604511` (main, success)
  - 구성 잡: `phase3-backend-policy-audit`, `phase3-frontend-typecheck`

원클릭 실행:
```bash
cd backend
./scripts/run_phase3_full_check.sh
```

MCP 스모크 포함 실행:
```bash
cd backend
RUN_MCP_SMOKE=1 API_BASE_URL=https://<your-api-domain> API_KEY=metel_xxx ./scripts/run_phase3_full_check.sh
```

정책/대시보드 자동검증 포함 실행:
```bash
cd backend
RUN_MCP_SMOKE=1 \
RUN_POLICY_SCENARIOS=1 \
RUN_DASHBOARD_CONSISTENCY=1 \
RUN_STRICT_HIGH_RISK=1 \
API_BASE_URL=https://<your-api-domain> \
API_KEY=metel_xxx \
USER_JWT=<user_jwt> \
./scripts/run_phase3_full_check.sh
```

사전 조건:
- Backend/Frontend 최신 코드 반영
- 테스트용 API Key 1개 이상 발급
- Notion/Linear OAuth 연결 완료(최소 1개 계정)

---

## 1) 로컬 자동 테스트

### 1-1. Phase3 회귀 테스트
```bash
cd backend
./scripts/run_phase3_regression.sh
```

기대 결과:
- 정책/API/Audit/멀티테넌시 테스트 전체 pass

### 1-2. Core 회귀 테스트
```bash
cd backend
./scripts/run_core_regression.sh
```

기대 결과:
- 기존 핵심 경로 회귀 없음

### 1-3. 프론트 타입체크
```bash
cd frontend
pnpm -s tsc --noEmit
```

기대 결과:
- 타입 오류 없음

---

## 2) 원격 CI 테스트

### 2-1. Phase3 워크플로우 실행
```bash
gh workflow run backend-phase3-regression.yml
gh run list --workflow="backend-phase3-regression.yml" --limit 3
gh run watch <run_id>
```

기대 결과:
- `phase3-backend-policy-audit` 성공
- `phase3-frontend-typecheck` 성공

---

## 3) MCP 스모크 테스트

### 3-1. 기본 스모크
```bash
cd backend
API_BASE_URL=https://<your-api-domain> MCP_BASE_URL=https://<your-api-domain>/mcp ./scripts/run_mcp_smoke.sh
```

기대 결과:
- `list_tools` 성공
- `notion_retrieve_bot_user` 성공
- `linear_get_viewer` 성공
- schema/risk gate 에러 케이스 정상 검증

---

## 4) 정책 기능 수동 테스트

자동화 스크립트:
```bash
cd backend
API_BASE_URL=https://<your-api-domain> USER_JWT=<user_jwt> ./scripts/run_phase3_policy_scenarios.sh
```

강화 모드(기본값):
- `RUN_STRICT_HIGH_RISK=1` 기본 적용
- 4-5 시나리오에서
  - high-risk 호출이 실제 success인지
  - `tool_calls.error_code=policy_override_allowed` 로그가 남는지
  둘 다 실패 시 테스트 실패 처리

## 4-1. `allowed_tools` 허용 제한
- API Key policy: `allowed_tools=["notion_retrieve_bot_user"]`
- `linear_get_viewer` 호출

기대 결과:
- `tool_not_allowed_for_api_key`

## 4-2. `deny_tools` 우선 차단
- API Key policy: `deny_tools=["linear_list_issues"]`
- `linear_list_issues` 호출

기대 결과:
- `access_denied`

## 4-3. `allowed_services` 제한
- API Key policy: `allowed_services=["notion"]`
- `linear_get_viewer` 호출

기대 결과:
- `service_not_allowed`

## 4-4. `allowed_linear_team_ids` 팀 제한
- API Key policy: `allowed_linear_team_ids=["team-a"]`
- `linear_create_issue` with `team_id="team-b"`

기대 결과:
- `access_denied` + `team_not_allowed`

## 4-5. `allow_high_risk` 예외 허용
- API Key policy: `allow_high_risk=true`
- high-risk tool payload 호출

기대 결과:
- 기본 차단이 아니라 허용되며 `policy_override_allowed` 로그 생성

---

## 5) 감사/Audit 검증

## 5-1. 이벤트 조회 API
```bash
curl -H "Authorization: Bearer <user_jwt>" \
  "https://<your-api-domain>/api/audit/events?limit=20&status=all"
```

기대 결과:
- actor/action/outcome/error/timestamp 필드 포함

## 5-2. 이벤트 Export API (jsonl/csv)
```bash
curl -L -H "Authorization: Bearer <user_jwt>" \
  "https://<your-api-domain>/api/audit/export?format=jsonl&limit=100"

curl -L -H "Authorization: Bearer <user_jwt>" \
  "https://<your-api-domain>/api/audit/export?format=csv&limit=100"
```

기대 결과:
- 파일 다운로드 성공
- jsonl/csv 형식 유효

---

## 6) 대시보드 검증

API 기반 자동검증:
```bash
cd backend
API_BASE_URL=https://<your-api-domain> USER_JWT=<user_jwt> ./scripts/run_phase3_dashboard_consistency.sh
```

확인 위치:
- Dashboard > MCP Usage
- Dashboard > Audit Events

검증 항목:
- `access_denied_24h`
- `high_risk_allowed_24h`
- `policy_override_usage_24h`
- Audit 요약 카드(`allowed/policy_blocked/access_denied/failed`)

기대 결과:
- API 결과와 대시보드 수치가 일치

---

## 7) 멀티테넌시 격리 검증

테스트 방식:
- 서로 다른 사용자 A/B 각각 API Key/JWT 사용
- A의 자격으로 B 데이터 조회 시도

기대 결과:
- A는 A의 `api_keys/tool_calls/audit` 데이터만 조회 가능
- 교차 조회 결과 없음

자동 검증 파일:
- `backend/tests/test_tenant_isolation_route.py`

---

## 8) 최종 판정 기준 (Go/No-Go)

Go 조건:
- 로컬 회귀/타입체크/원격 CI 모두 성공
- 정책 차단/허용 시나리오 기대값 일치
- Audit 조회/Export 정상
- 대시보드 지표 정상 반영
- 멀티테넌시 격리 확인 완료

No-Go 조건:
- 하나라도 실패하거나 로그/지표 불일치 발생
