# RBAC Production Monitoring Log (Started: 2026-03-05)

목적:
- production full guard 활성 이후 48시간 동안 권한 이상 징후를 관측한다.

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
| 0h | 2026-03-05 | PASS | `run_rbac_rollout_stage_gate.sh` full_guard 통과, `run_rbac_monitoring_snapshot.sh` OK |
| 1h | pending | pending |  |
| 2h | pending | pending |  |
| 6h | pending | pending |  |
| 12h | pending | pending |  |
| 24h | pending | pending |  |
| 36h | pending | pending |  |
| 48h | pending | pending |  |

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


# 실행 명령어
## backend 디렉토리에서 실행
export API_BASE_URL="https://metel-production.up.railway.app"
export OWNER_JWT='...'
export ADMIN_JWT='...'
export MEMBER_JWT='...'

## 값 확인(비어있지 않아야 함)
echo ${#OWNER_JWT} ${#ADMIN_JWT} ${#MEMBER_JWT}

MODE=full_guard ./scripts/run_rbac_rollout_stage_gate.sh
./scripts/run_rbac_monitoring_snapshot.sh


# 모니터링 결과

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
  audit_failed_count=0
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


