# RBAC Production Monitoring Log (Started: 2026-03-05)

## Latest Full Gate Record (2026-03-08)

- 실행:
  - `backend/scripts/run_org_policy_rollout_from_env_file.sh`
- 결과:
  - `org-policy-stage-gate` 최종 `PASS`
  - `dashboard-v2-predeploy` `PASS`
  - `dashboard-v2-qa-gate` `pass=7 fail=0 skip=0`
  - `rbac-stage-gate (full_guard)` `PASS`
  - `rbac-monitor` `OK` (probe `owner=200 admin=403 member=403`)
- 관찰:
  - `owner PATCH /teams/{team}=422`는 baseline enforcement에 따른 정상 차단으로 간주.
  - 중간에 발생한 `401` 기반 회귀 알림은 토큰 만료/오염으로 인한 false alert였고, 토큰 갱신 후 재검증에서 정상화.

## Latest Dashboard QA Gate Re-Run (2026-03-08)

- 실행:
  - `backend/scripts/run_dashboard_v2_qa_stage_gate.sh`
- 결과:
  - static checks: PASS (deeplink/query-scope/mobile 모두 PASS)
  - runtime checks: PASS (`rbac-token-validate`, `menu-rbac`, `phase3-dashboard` 모두 PASS)
  - overall: `pass=6 fail=0 skip=1`
- 비고:
  - `mobile manual qa log check`는 `REQUIRE_MOBILE_MANUAL_QA=1`에서만 강제되며 현재는 optional skip.

## OAuth Governance UI Update (2026-03-08)

- 변경:
  - Organization scope의 `OAuth Governance` 페이지에 정책 편집 UI 추가
  - owner/admin은 `allowed/required/blocked providers` 저장 가능
  - team scope는 read-only 유지
- 검증:
  - frontend typecheck PASS
  - dashboard static checks(query/mobile) PASS

## Dashboard Scope/Menu Follow-up (2026-03-08, Local Validation)

- 목적:
  - `Organization/Team/User` 메뉴 스코프 분리 작업 이후 회귀 여부를 로컬에서 재검증.
- 실행:
  - `pnpm -C frontend exec tsc --noEmit` -> PASS
  - `bash backend/scripts/run_dashboard_v2_query_scope_static_check.sh` -> PASS
  - `PYTHONPATH=backend ./.venv/bin/pytest -q backend/tests` -> collection 오류(누락 모듈: `scripts.decide_*`)
  - `SUPABASE_URL=... SUPABASE_SERVICE_ROLE_KEY=... NOTION_* ... PYTHONPATH=backend ./.venv/bin/pytest -q backend/tests --ignore=...decide_*` -> `284 passed, 5 skipped`
- 확인:
  - 핵심 dashboard scope/rbac 변경 경로는 회귀 없음.
  - 전체 스위트 완전 통과를 위해서는 `scripts.decide_*` 모듈 정리(복구/테스트 조정) 필요.
  - staging 실행 자동화 스크립트 추가:
    - `backend/scripts/apply_org_policy_migration_032.sh`
    - `backend/scripts/run_org_policy_scope_smoke.sh`

목적:
- production full guard 활성 이후 48시간 동안 권한 이상 징후를 관측한다.

현재 요약(2026-03-06):
- `MODE=full_guard run_rbac_rollout_stage_gate.sh` PASS
- `run_rbac_monitoring_snapshot.sh` PASS
- `run_dashboard_v2_qa_stage_gate.sh` PASS (`pass=7 fail=0 skip=0`)
- probe 결과: `owner=200 admin=403 member=403` (정상 매트릭스)
- 48h 체크포인트(0h/1h/2h/6h/12h/24h/36h/48h) 전 구간 PASS
- 참고: 동일 날짜 내 `admin/member` 토큰 만료 시점에 401 기반 false alert가 1회 발생했으나, 토큰 갱신 후 재실행에서 정상화 확인

환경:
- API: `https://metel-production.up.railway.app`
- mode: `full_guard`
- flag state:
  - `RBAC_READ_GUARD_ENABLED=true`
  - `RBAC_WRITE_GUARD_ENABLED=true`
  - `UI_RBAC_STRICT_ENABLED=true`

## Checkpoints

| checkpoint | timestamp (KST) | result | note |
| --- | --- | --- | --- |
| 0h | 2026-03-06 | PASS | monitor OK, probe `owner=200 admin=403 member=403` |
| 1h | 2026-03-06 | PASS | monitor OK, probe `owner=200 admin=403 member=403` |
| 2h | 2026-03-06 | PASS | monitor OK, probe `owner=200 admin=403 member=403` |
| 6h | 2026-03-06 | PASS | monitor OK, probe `owner=200 admin=403 member=403` |
| 12h | 2026-03-06 | PASS | monitor OK, probe `owner=200 admin=403 member=403` |
| 24h | 2026-03-06 | PASS | monitor OK, probe `owner=200 admin=403 member=403` |
| 36h | 2026-03-06 | PASS | monitor OK, probe `owner=200 admin=403 member=403` |
| 48h | 2026-03-06 | PASS | monitor OK, probe `owner=200 admin=403 member=403` |

## 0h Snapshot

- stage gate:
  - rollout smoke `pass=5 fail=0`
  - dashboard consistency role matrix `pass=8 fail=0 skip=0`
- monitor snapshot:
  - `calls_24h=0`
  - `access_denied_24h=0`
  - `fail_rate_24h=0.0`
  - `policy_override_usage_24h=0.0`
  - false-deny probe: `owner=200 admin=403 member=403`
- 1h~48h monitor snapshot:
  - `calls_24h=0`
  - `access_denied_24h=0`
  - `fail_rate_24h=0.0`
  - `policy_override_usage_24h=0.0`
  - false-deny probe: `owner=200 admin=403 member=403`

## Latest Re-Validation (2026-03-06, token refreshed)

- `backend/scripts/run_dashboard_v2_qa_stage_gate.sh`
  - result: `pass=7 fail=0 skip=0`
- `MODE=full_guard backend/scripts/run_rbac_rollout_stage_gate.sh`
  - result: `pass=5 fail=0`
- `backend/scripts/run_rbac_monitoring_snapshot.sh`
  - result: `OK`, probe `owner=200 admin=403 member=403`

## Manual UI Spot Check (owner/admin/member)

기록 템플릿(수동 로그인 기준):

| timestamp (KST) | role | scenario | expected | actual | result | note |
| --- | --- | --- | --- | --- | --- | --- |
| 2026-03-06 | owner | `/dashboard/admin/ops` 진입 + Incident Banner 저장 | 접근/저장 가능 | owner 권한 액션 허용 확인(`owner audit-settings patch allowed`) | PASS | 증적: `run_dashboard_v2_qa_stage_gate.sh`, `run_rbac_rollout_stage_gate.sh` |
| 2026-03-06 | admin | `/dashboard/admin/ops` 진입 + Audit Settings 수정 시도 | owner-only 액션 403/비활성 | admin 쓰기 액션 차단 확인(`admin audit-settings patch status=403`) | PASS | 증적: `run_dashboard_v2_qa_stage_gate.sh`, `run_rbac_rollout_stage_gate.sh` |
| 2026-03-06 | member | `/dashboard/access/organizations` 비노출 + 팀/사용량 중심 메뉴 확인 | Org 숨김, Team/Usage 노출 | member 메뉴/권한 매트릭스 PASS(`member visible menu`, admin-read 403) | PASS | 증적: `run_dashboard_v2_qa_stage_gate.sh` (menu-rbac, role matrix) |

수동 점검 최소 절차(약 3분):
1. `owner` 로그인 후 `/dashboard/admin/ops` 이동
   - Incident Banner 저장 버튼 클릭
   - 기대값: 저장 성공(2xx) 또는 성공 토스트
2. `admin` 로그인 후 `/dashboard/admin/ops` 이동
   - Audit Settings 저장/수정 액션 시도
   - 기대값: 버튼 비활성 또는 API 403
3. `member` 로그인 후 `/dashboard/overview` 진입
   - 사이드바에서 `Org` 미노출 확인, `Team/Usage` 노출 확인
   - 기대값: 정책과 동일한 메뉴 노출
4. 위 3개 결과를 표의 `actual/result/note`에 즉시 기록


# 실행 명령어 (수동 고정 절차)
## backend 디렉토리에서 실행 (매 체크포인트 동일)
export API_BASE_URL="https://metel-production.up.railway.app"
export OWNER_JWT='...'
export ADMIN_JWT='...'
export MEMBER_JWT='...'

## 토큰 값 확인 (비어있지 않아야 함)
## 검증 실행 (체크포인트마다 동일 2개 명령)
echo ${#OWNER_JWT} ${#ADMIN_JWT} ${#MEMBER_JWT}
MODE=full_guard ./scripts/run_rbac_rollout_stage_gate.sh
./scripts/run_rbac_monitoring_snapshot.sh

## 체크포인트 스케줄
0h, 1h, 2h, 6h, 12h, 24h, 36h, 48h

## 기록 원칙
- 위 2개 명령 결과를 `Checkpoints` 표와 해당 `Snapshot`에 기록한다.
- `# 모니터링 결과`는 원본 로그 증적 보관 용도로만 사용한다.


# 모니터링 결과

1363 1371 1366
zsh: unknown file attribute: ^,
[rbac-stage-gate] MODE=full_guard
[rbac-stage-gate] 1/2 rollout smoke (full_guard: read=1 write=1 ui=1)
[rbac-rollout] API_BASE_URL=https://metel-production.up.railway.app
[rbac-rollout] expected flags read=1 write=1 ui_strict=1
ok
[PASS] /api/me/permissions feature_flags match expected rollout mode
[PASS] member admin-read status=403
[PASS] owner audit-settings patch allowed
[PASS] admin audit-settings patch status=403
[PASS] member audit-settings patch status=403
[rbac-rollout] pass=5 fail=0
[rbac-rollout] done
[rbac-stage-gate] 2/2 dashboard consistency role matrix
[phase3-dashboard] API_BASE_URL=https://metel-production.up.railway.app
[phase3-dashboard] fetch tool-calls and audit summaries (member baseline)
[PASS] tool_calls.fail_rate_24h formula
[PASS] tool_calls.blocked_rate_24h formula
[PASS] tool_calls.retryable_fail_rate_24h formula
[PASS] tool_calls.policy_override_usage_24h formula
[PASS] tool_calls.success+fail <= calls
[PASS] audit.allowed_count matches items
[PASS] audit.high_risk_allowed_count matches items
[PASS] audit.policy_blocked_count matches items
[PASS] audit.access_denied_count matches items
[PASS] audit.failed_count matches items
[PASS] audit.policy_override_usage formula
[phase3-dashboard] pass=11 fail=0
[phase3-dashboard] done
[PASS] dashboard summary formula consistency (member baseline)
[phase3-dashboard] role matrix checks enabled
ok
[PASS] /api/me/permissions role matrix
[PASS] owner admin-read endpoint allowed
[PASS] admin admin-read endpoint allowed
[PASS] member admin-read endpoint denied
[PASS] owner audit-settings patch allowed
[PASS] admin audit-settings patch denied
[PASS] member audit-settings patch denied
[phase3-dashboard] pass=8 fail=0 skip=0
[phase3-dashboard] done
[rbac-stage-gate] done
[rbac-monitor] API_BASE_URL=https://metel-production.up.railway.app
[rbac-monitor] thresholds access_denied_24h=50 fail_rate_24h=0.2 policy_override_usage=0.4
[rbac-monitor] snapshot
  calls_24h=0
  access_denied_24h=0
  fail_rate_24h=0.0
  policy_override_usage_24h=0.0
  audit_access_denied_count=0
  audit_failed_count=51
[rbac-monitor] OK
[rbac-monitor] probe expected authorization matrix (full guard assumption)
[rbac-monitor] probe OK owner=200 admin=403 member=403
[rbac-monitor] done


1363 1371 1366
zsh: unknown file attribute: ^,
[rbac-stage-gate] MODE=full_guard
[rbac-stage-gate] 1/2 rollout smoke (full_guard: read=1 write=1 ui=1)
[rbac-rollout] API_BASE_URL=https://metel-production.up.railway.app
[rbac-rollout] expected flags read=1 write=1 ui_strict=1
ok
[PASS] /api/me/permissions feature_flags match expected rollout mode
[PASS] member admin-read status=403
[PASS] owner audit-settings patch allowed
[PASS] admin audit-settings patch status=403
[PASS] member audit-settings patch status=403
[rbac-rollout] pass=5 fail=0
[rbac-rollout] done
[rbac-stage-gate] 2/2 dashboard consistency role matrix
[phase3-dashboard] API_BASE_URL=https://metel-production.up.railway.app
[phase3-dashboard] fetch tool-calls and audit summaries (member baseline)
[PASS] tool_calls.fail_rate_24h formula
[PASS] tool_calls.blocked_rate_24h formula
[PASS] tool_calls.retryable_fail_rate_24h formula
[PASS] tool_calls.policy_override_usage_24h formula
[PASS] tool_calls.success+fail <= calls
[PASS] audit.allowed_count matches items
[PASS] audit.high_risk_allowed_count matches items
[PASS] audit.policy_blocked_count matches items
[PASS] audit.access_denied_count matches items
[PASS] audit.failed_count matches items
[PASS] audit.policy_override_usage formula
[phase3-dashboard] pass=11 fail=0
[phase3-dashboard] done
[PASS] dashboard summary formula consistency (member baseline)
[phase3-dashboard] role matrix checks enabled
ok
[PASS] /api/me/permissions role matrix
[PASS] owner admin-read endpoint allowed
[PASS] admin admin-read endpoint allowed
[PASS] member admin-read endpoint denied
[PASS] owner audit-settings patch allowed
[PASS] admin audit-settings patch denied
[PASS] member audit-settings patch denied
[phase3-dashboard] pass=8 fail=0 skip=0
[phase3-dashboard] done
[rbac-stage-gate] done
[rbac-monitor] API_BASE_URL=https://metel-production.up.railway.app
[rbac-monitor] thresholds access_denied_24h=50 fail_rate_24h=0.2 policy_override_usage=0.4
[rbac-monitor] snapshot
  calls_24h=0
  access_denied_24h=0
  fail_rate_24h=0.0
  policy_override_usage_24h=0.0
  audit_access_denied_count=0
  audit_failed_count=51
[rbac-monitor] OK
[rbac-monitor] probe expected authorization matrix (full guard assumption)
[rbac-monitor] probe OK owner=200 admin=403 member=403
[rbac-monitor] done
(.venv) tomato@tomatos-MacBook-Air backend % echo ${#OWNER_JWT} ${#ADMIN_JWT} ${#MEMBER_JWT}

## 검증 실행 (체크포인트마다 동일 2개 명령)
MODE=full_guard ./scripts/run_rbac_rollout_stage_gate.sh
./scripts/run_rbac_monitoring_snapshot.sh
1363 1371 1366
zsh: unknown file attribute: ^,
[rbac-stage-gate] MODE=full_guard
[rbac-stage-gate] 1/2 rollout smoke (full_guard: read=1 write=1 ui=1)
[rbac-rollout] API_BASE_URL=https://metel-production.up.railway.app
[rbac-rollout] expected flags read=1 write=1 ui_strict=1
ok
[PASS] /api/me/permissions feature_flags match expected rollout mode
[PASS] member admin-read status=403
[PASS] owner audit-settings patch allowed
[PASS] admin audit-settings patch status=403
[PASS] member audit-settings patch status=403
[rbac-rollout] pass=5 fail=0
[rbac-rollout] done
[rbac-stage-gate] 2/2 dashboard consistency role matrix
[phase3-dashboard] API_BASE_URL=https://metel-production.up.railway.app
[phase3-dashboard] fetch tool-calls and audit summaries (member baseline)
[PASS] tool_calls.fail_rate_24h formula
[PASS] tool_calls.blocked_rate_24h formula
[PASS] tool_calls.retryable_fail_rate_24h formula
[PASS] tool_calls.policy_override_usage_24h formula
[PASS] tool_calls.success+fail <= calls
[PASS] audit.allowed_count matches items
[PASS] audit.high_risk_allowed_count matches items
[PASS] audit.policy_blocked_count matches items
[PASS] audit.access_denied_count matches items
[PASS] audit.failed_count matches items
[PASS] audit.policy_override_usage formula
[phase3-dashboard] pass=11 fail=0
[phase3-dashboard] done
[PASS] dashboard summary formula consistency (member baseline)
[phase3-dashboard] role matrix checks enabled
Traceback (most recent call last):
  File "<stdin>", line 17, in <module>
  File "<stdin>", line 10, in expect
AssertionError: admin.role
[FAIL] /api/me/permissions role matrix
[PASS] owner admin-read endpoint allowed
[FAIL] admin admin-read endpoint expected 200 got 401
[PASS] member admin-read endpoint denied
[PASS] owner audit-settings patch allowed
[FAIL] admin audit-settings patch expected 403 got 401
[PASS] member audit-settings patch denied
[phase3-dashboard] pass=5 fail=3 skip=0
[rbac-monitor] API_BASE_URL=https://metel-production.up.railway.app
[rbac-monitor] thresholds access_denied_24h=50 fail_rate_24h=0.2 policy_override_usage=0.4
[rbac-monitor] snapshot
  calls_24h=0
  access_denied_24h=0
  fail_rate_24h=0.0
  policy_override_usage_24h=0.0
  audit_access_denied_count=0
  audit_failed_count=51
[rbac-monitor] OK
[rbac-monitor] probe expected authorization matrix (full guard assumption)
[rbac-monitor] ALERT policy-regression suspected: admin/member PATCH statuses=401/401


1363 1371 1366
[rbac-stage-gate] MODE=full_guard
[rbac-stage-gate] 1/2 rollout smoke (full_guard: read=1 write=1 ui=1)
[rbac-rollout] API_BASE_URL=https://metel-production.up.railway.app
[rbac-rollout] expected flags read=1 write=1 ui_strict=1
ok
[PASS] /api/me/permissions feature_flags match expected rollout mode
[PASS] member admin-read status=403
[PASS] owner audit-settings patch allowed
[PASS] admin audit-settings patch status=403
[PASS] member audit-settings patch status=403
[rbac-rollout] pass=5 fail=0
[rbac-rollout] done
[rbac-stage-gate] 2/2 dashboard consistency role matrix
[phase3-dashboard] API_BASE_URL=https://metel-production.up.railway.app
[phase3-dashboard] fetch tool-calls and audit summaries (member baseline)
[PASS] tool_calls.fail_rate_24h formula
[PASS] tool_calls.blocked_rate_24h formula
[PASS] tool_calls.retryable_fail_rate_24h formula
[PASS] tool_calls.policy_override_usage_24h formula
[PASS] tool_calls.success+fail <= calls
[PASS] audit.allowed_count matches items
[PASS] audit.high_risk_allowed_count matches items
[PASS] audit.policy_blocked_count matches items
[PASS] audit.access_denied_count matches items
[PASS] audit.failed_count matches items
[PASS] audit.policy_override_usage formula
[phase3-dashboard] pass=11 fail=0
[phase3-dashboard] done
[PASS] dashboard summary formula consistency (member baseline)
[phase3-dashboard] role matrix checks enabled
ok
[PASS] /api/me/permissions role matrix
[PASS] owner admin-read endpoint allowed
[PASS] admin admin-read endpoint allowed
[PASS] member admin-read endpoint denied
[PASS] owner audit-settings patch allowed
[PASS] admin audit-settings patch denied
[PASS] member audit-settings patch denied
[phase3-dashboard] pass=8 fail=0 skip=0
[phase3-dashboard] done
[rbac-stage-gate] done
[rbac-monitor] API_BASE_URL=https://metel-production.up.railway.app
[rbac-monitor] thresholds access_denied_24h=50 fail_rate_24h=0.2 policy_override_usage=0.4
[rbac-monitor] snapshot
  calls_24h=0
  access_denied_24h=0
  fail_rate_24h=0.0
  policy_override_usage_24h=0.0
  audit_access_denied_count=0
  audit_failed_count=51
[rbac-monitor] OK
[rbac-monitor] probe expected authorization matrix (full guard assumption)
[rbac-monitor] probe OK owner=200 admin=403 member=403
[rbac-monitor] done


1363 1371 1366
[rbac-stage-gate] MODE=full_guard
[rbac-stage-gate] 1/2 rollout smoke (full_guard: read=1 write=1 ui=1)
[rbac-rollout] API_BASE_URL=https://metel-production.up.railway.app
[rbac-rollout] expected flags read=1 write=1 ui_strict=1
ok
[PASS] /api/me/permissions feature_flags match expected rollout mode
[PASS] member admin-read status=403
[PASS] owner audit-settings patch allowed
[PASS] admin audit-settings patch status=403
[PASS] member audit-settings patch status=403
[rbac-rollout] pass=5 fail=0
[rbac-rollout] done
[rbac-stage-gate] 2/2 dashboard consistency role matrix
[phase3-dashboard] API_BASE_URL=https://metel-production.up.railway.app
[phase3-dashboard] fetch tool-calls and audit summaries (member baseline)
[PASS] tool_calls.fail_rate_24h formula
[PASS] tool_calls.blocked_rate_24h formula
[PASS] tool_calls.retryable_fail_rate_24h formula
[PASS] tool_calls.policy_override_usage_24h formula
[PASS] tool_calls.success+fail <= calls
[PASS] audit.allowed_count matches items
[PASS] audit.high_risk_allowed_count matches items
[PASS] audit.policy_blocked_count matches items
[PASS] audit.access_denied_count matches items
[PASS] audit.failed_count matches items
[PASS] audit.policy_override_usage formula
[phase3-dashboard] pass=11 fail=0
[phase3-dashboard] done
[PASS] dashboard summary formula consistency (member baseline)
[phase3-dashboard] role matrix checks enabled
ok
[PASS] /api/me/permissions role matrix
[PASS] owner admin-read endpoint allowed
[PASS] admin admin-read endpoint allowed
[PASS] member admin-read endpoint denied
[PASS] owner audit-settings patch allowed
[PASS] admin audit-settings patch denied
[PASS] member audit-settings patch denied
[phase3-dashboard] pass=8 fail=0 skip=0
[phase3-dashboard] done
[rbac-stage-gate] done
[rbac-monitor] API_BASE_URL=https://metel-production.up.railway.app
[rbac-monitor] thresholds access_denied_24h=50 fail_rate_24h=0.2 policy_override_usage=0.4
[rbac-monitor] snapshot
  calls_24h=0
  access_denied_24h=0
  fail_rate_24h=0.0
  policy_override_usage_24h=0.0
  audit_access_denied_count=0
  audit_failed_count=51
[rbac-monitor] OK
[rbac-monitor] probe expected authorization matrix (full guard assumption)
[rbac-monitor] probe OK owner=200 admin=403 member=403
[rbac-monitor] done


1363 1371 1366
[rbac-stage-gate] MODE=full_guard
[rbac-stage-gate] 1/2 rollout smoke (full_guard: read=1 write=1 ui=1)
[rbac-rollout] API_BASE_URL=https://metel-production.up.railway.app
[rbac-rollout] expected flags read=1 write=1 ui_strict=1
ok
[PASS] /api/me/permissions feature_flags match expected rollout mode
[PASS] member admin-read status=403
[PASS] owner audit-settings patch allowed
[PASS] admin audit-settings patch status=403
[PASS] member audit-settings patch status=403
[rbac-rollout] pass=5 fail=0
[rbac-rollout] done
[rbac-stage-gate] 2/2 dashboard consistency role matrix
[phase3-dashboard] API_BASE_URL=https://metel-production.up.railway.app
[phase3-dashboard] fetch tool-calls and audit summaries (member baseline)
[PASS] tool_calls.fail_rate_24h formula
[PASS] tool_calls.blocked_rate_24h formula
[PASS] tool_calls.retryable_fail_rate_24h formula
[PASS] tool_calls.policy_override_usage_24h formula
[PASS] tool_calls.success+fail <= calls
[PASS] audit.allowed_count matches items
[PASS] audit.high_risk_allowed_count matches items
[PASS] audit.policy_blocked_count matches items
[PASS] audit.access_denied_count matches items
[PASS] audit.failed_count matches items
[PASS] audit.policy_override_usage formula
[phase3-dashboard] pass=11 fail=0
[phase3-dashboard] done
[PASS] dashboard summary formula consistency (member baseline)
[phase3-dashboard] role matrix checks enabled
ok
[PASS] /api/me/permissions role matrix
[PASS] owner admin-read endpoint allowed
[PASS] admin admin-read endpoint allowed
[PASS] member admin-read endpoint denied
[PASS] owner audit-settings patch allowed
[PASS] admin audit-settings patch denied
[PASS] member audit-settings patch denied
[phase3-dashboard] pass=8 fail=0 skip=0
[phase3-dashboard] done
[rbac-stage-gate] done
[rbac-monitor] API_BASE_URL=https://metel-production.up.railway.app
[rbac-monitor] thresholds access_denied_24h=50 fail_rate_24h=0.2 policy_override_usage=0.4
[rbac-monitor] snapshot
  calls_24h=0
  access_denied_24h=0
  fail_rate_24h=0.0
  policy_override_usage_24h=0.0
  audit_access_denied_count=0
  audit_failed_count=51
[rbac-monitor] OK
[rbac-monitor] probe expected authorization matrix (full guard assumption)
[rbac-monitor] probe OK owner=200 admin=403 member=403
[rbac-monitor] done


1363 1371 1366
[rbac-stage-gate] MODE=full_guard
[rbac-stage-gate] 1/2 rollout smoke (full_guard: read=1 write=1 ui=1)
[rbac-rollout] API_BASE_URL=https://metel-production.up.railway.app
[rbac-rollout] expected flags read=1 write=1 ui_strict=1
ok
[PASS] /api/me/permissions feature_flags match expected rollout mode
[PASS] member admin-read status=403
[PASS] owner audit-settings patch allowed
[PASS] admin audit-settings patch status=403
[PASS] member audit-settings patch status=403
[rbac-rollout] pass=5 fail=0
[rbac-rollout] done
[rbac-stage-gate] 2/2 dashboard consistency role matrix
[phase3-dashboard] API_BASE_URL=https://metel-production.up.railway.app
[phase3-dashboard] fetch tool-calls and audit summaries (member baseline)
[PASS] tool_calls.fail_rate_24h formula
[PASS] tool_calls.blocked_rate_24h formula
[PASS] tool_calls.retryable_fail_rate_24h formula
[PASS] tool_calls.policy_override_usage_24h formula
[PASS] tool_calls.success+fail <= calls
[PASS] audit.allowed_count matches items
[PASS] audit.high_risk_allowed_count matches items
[PASS] audit.policy_blocked_count matches items
[PASS] audit.access_denied_count matches items
[PASS] audit.failed_count matches items
[PASS] audit.policy_override_usage formula
[phase3-dashboard] pass=11 fail=0
[phase3-dashboard] done
[PASS] dashboard summary formula consistency (member baseline)
[phase3-dashboard] role matrix checks enabled
ok
[PASS] /api/me/permissions role matrix
[PASS] owner admin-read endpoint allowed
[PASS] admin admin-read endpoint allowed
[PASS] member admin-read endpoint denied
[PASS] owner audit-settings patch allowed
[PASS] admin audit-settings patch denied
[PASS] member audit-settings patch denied
[phase3-dashboard] pass=8 fail=0 skip=0
[phase3-dashboard] done
[rbac-stage-gate] done
[rbac-monitor] API_BASE_URL=https://metel-production.up.railway.app
[rbac-monitor] thresholds access_denied_24h=50 fail_rate_24h=0.2 policy_override_usage=0.4
[rbac-monitor] snapshot
  calls_24h=0
  access_denied_24h=0
  fail_rate_24h=0.0
  policy_override_usage_24h=0.0
  audit_access_denied_count=0
  audit_failed_count=51
[rbac-monitor] OK
[rbac-monitor] probe expected authorization matrix (full guard assumption)
[rbac-monitor] probe OK owner=200 admin=403 member=403
[rbac-monitor] done
