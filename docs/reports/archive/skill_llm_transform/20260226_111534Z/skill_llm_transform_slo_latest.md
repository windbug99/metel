# Agent Quality Report

- sample size: 109 (min required: 30)
- autonomous success rate: 97.2% (35/36, target >= 80.0%)
- autonomous attempt rate: 67.9% (74/109)
- autonomous success over attempts: 47.3% (35/74)
- llm planner failed rate: 0.0% (0/109, target <= 20.0%)
- verification failed rate: 0.0% (0/109, target <= 25.0%)
- guardrail degrade rate: 13.8% (15/109, target <= 40.0%)
- fallback rate: 35.8% (39/109, target <= 10.0%)
- verdict: FAIL

## Plan Source Distribution
- llm: 62
- rule: 22
- dag_template: 17
- calendar_linear_template: 4
- rule_recent_lookup: 4

## Execution Mode Distribution
- rule: 73
- autonomous: 36

## Top Fallback Reasons
- tool_error_rate: 15
- replan_limit: 8
- TOOL_TIMEOUT: 5
- auth_error: 3
- validation_error: 3

## Top Error Codes
- auth_error: 18
- TOOL_TIMEOUT: 5
- validation_error: 3
- COMPENSATION_FAILED: 3
- execution_failed: 3

## Top Guardrail Degrade Reasons
- tool_error_rate: 15

## Tuning Hints
- 도구 오류율 기반 강등이 잦습니다. payload 정규화와 스키마 자동보정 정책을 강화하세요.
- replan_limit 비중이 높습니다. replan 조건을 줄이고 초기 tool ranking 품질을 먼저 개선하세요.

## Policy Recommendations
- `LLM_HYBRID_EXECUTOR_FIRST=true`: 가드레일 강등 비중이 높아 안정 구간에서 deterministic-first 운용이 필요합니다.
- `LLM_AUTONOMOUS_REPLAN_LIMIT=2`: replan_limit 비중이 높아 재계획 허용 횟수 상향이 필요합니다.
- `TOOL_SPECS_VALIDATE_ON_STARTUP=true`: 초기 검증/구성 점검을 강화해 인증 관련 실패를 조기 탐지하세요.

## Gate Reasons
- fallback_rate_above_target: 0.358 > 0.100
- autonomous_success_over_attempt_below_target: 0.473 < 0.700
