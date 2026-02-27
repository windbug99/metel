# Agent Quality Report

- sample size: 199 (min required: 30)
- autonomous success rate: 91.7% (121/132, target >= 80.0%)
- autonomous attempt rate: 89.9% (179/199)
- autonomous success over attempts: 67.6% (121/179)
- llm planner failed rate: 0.0% (0/199, target <= 20.0%)
- verification failed rate: 0.5% (1/199, target <= 25.0%)
- guardrail degrade rate: 13.1% (26/199, target <= 40.0%)
- fallback rate: 36.7% (73/199, target <= 10.0%)
- verdict: FAIL

## Plan Source Distribution
- llm: 131
- rule: 55
- dag_template: 9
- rule_recent_lookup: 4

## Execution Mode Distribution
- autonomous: 132
- rule: 67

## Top Fallback Reasons
- replan_limit: 32
- tool_error_rate: 26
- auth_error: 3
- validation_error: 3
- COMPENSATION_FAILED: 3

## Top Verification Reasons
- mutation_requires_mutation_tool: 2

## Top Error Codes
- auth_error: 24
- replan_limit: 10
- validation_error: 7
- execution_failed: 5
- COMPENSATION_FAILED: 3

## Top Guardrail Degrade Reasons
- tool_error_rate: 26

## Tuning Hints
- replan_limit 비중이 높습니다. replan 조건을 줄이고 초기 tool ranking 품질을 먼저 개선하세요.
- 도구 오류율 기반 강등이 잦습니다. payload 정규화와 스키마 자동보정 정책을 강화하세요.

## Policy Recommendations
- `LLM_AUTONOMOUS_REPLAN_LIMIT=2`: replan_limit 비중이 높아 재계획 허용 횟수 상향이 필요합니다.
- `LLM_HYBRID_EXECUTOR_FIRST=true`: 가드레일 강등 비중이 높아 안정 구간에서 deterministic-first 운용이 필요합니다.
- `TOOL_SPECS_VALIDATE_ON_STARTUP=true`: 초기 검증/구성 점검을 강화해 인증 관련 실패를 조기 탐지하세요.

## Gate Reasons
- fallback_rate_above_target: 0.367 > 0.100
- autonomous_success_over_attempt_below_target: 0.676 < 0.700
