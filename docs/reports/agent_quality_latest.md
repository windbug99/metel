# Agent Quality Report

- sample size: 30 (min required: 20)
- autonomous success rate: 72.7% (16/22, target >= 80.0%)
- autonomous attempt rate: 100.0% (30/30)
- autonomous success over attempts: 53.3% (16/30)
- llm planner failed rate: 0.0% (0/30, target <= 20.0%)
- verification failed rate: 3.3% (1/30, target <= 25.0%)
- guardrail degrade rate: 23.3% (7/30, target <= 40.0%)
- fallback rate: 63.3% (19/30, target <= 20.0%)
- verdict: FAIL

## Plan Source Distribution
- llm: 23
- rule: 7

## Execution Mode Distribution
- autonomous: 22
- rule: 8

## Top Fallback Reasons
- replan_limit: 11
- tool_error_rate: 7
- mutation_requires_mutation_tool: 1

## Top Verification Reasons
- mutation_requires_mutation_tool: 2

## Top Error Codes
- replan_limit: 5
- auth_error: 4
- validation_error: 2
- service_not_connected: 1
- verification_failed: 1

## Top Guardrail Degrade Reasons
- tool_error_rate: 7

## Tuning Hints
- replan_limit 비중이 높습니다. replan 조건을 줄이고 초기 tool ranking 품질을 먼저 개선하세요.
- 도구 오류율 기반 강등이 잦습니다. payload 정규화와 스키마 자동보정 정책을 강화하세요.
- verification_failed 비중이 높습니다. intent별 완료조건(verifier)을 세분화하고 final 허용 조건을 강화하세요.

## Policy Recommendations
- `LLM_AUTONOMOUS_REPLAN_LIMIT=2`: replan_limit 비중이 높아 재계획 허용 횟수 상향이 필요합니다.
- `LLM_HYBRID_EXECUTOR_FIRST=true`: 가드레일 강등 비중이 높아 안정 구간에서 deterministic-first 운용이 필요합니다.
- `TOOL_SPECS_VALIDATE_ON_STARTUP=true`: 초기 검증/구성 점검을 강화해 인증 관련 실패를 조기 탐지하세요.
- `LLM_AUTONOMOUS_LIMIT_RETRY_ONCE=true`: 검증 실패 비중이 높아 자동 재시도 정책 유지/활성화가 필요합니다.
- `LLM_AUTONOMOUS_RULE_FALLBACK_MUTATION_ENABLED=false`: mutation 요청은 rule fallback 대신 자율 재시도로 수렴시키는 것이 유리합니다.

## Gate Reasons
- autonomous_success_rate_below_target: 0.727 < 0.800
- fallback_rate_above_target: 0.633 > 0.200
- autonomous_success_over_attempt_below_target: 0.533 < 0.700
