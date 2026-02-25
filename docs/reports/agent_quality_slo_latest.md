# Agent Quality Report

- sample size: 300 (min required: 20)
- autonomous success rate: 88.2% (127/144, target >= 80.0%)
- autonomous attempt rate: 69.3% (208/300)
- autonomous success over attempts: 61.1% (127/208)
- llm planner failed rate: 0.0% (0/300, target <= 20.0%)
- verification failed rate: 0.7% (2/300, target <= 25.0%)
- guardrail degrade rate: 7.3% (22/300, target <= 40.0%)
- fallback rate: 35.7% (107/300, target <= 10.0%)
- verdict: FAIL

## Plan Source Distribution
- llm: 136
- dag_template: 57
- rule: 55
- router_v2: 52

## Execution Mode Distribution
- autonomous: 144
- rule: 104
- router_v2: 52

## Top Fallback Reasons
- replan_limit: 40
- tool_error_rate: 22
- TOOL_TIMEOUT: 17
- llm_unavailable: 6
- calendar_pipeline_failed: 3

## Top Verification Reasons
- mutation_requires_mutation_tool: 3

## Top Error Codes
- auth_error: 20
- TOOL_TIMEOUT: 17
- replan_limit: 15
- validation_error: 6
- llm_unavailable: 6

## Top Guardrail Degrade Reasons
- tool_error_rate: 22

## Tuning Hints
- replan_limit 비중이 높습니다. replan 조건을 줄이고 초기 tool ranking 품질을 먼저 개선하세요.
- 도구 오류율 기반 강등이 잦습니다. payload 정규화와 스키마 자동보정 정책을 강화하세요.

## Policy Recommendations
- `LLM_AUTONOMOUS_REPLAN_LIMIT=2`: replan_limit 비중이 높아 재계획 허용 횟수 상향이 필요합니다.
- `LLM_HYBRID_EXECUTOR_FIRST=true`: 가드레일 강등 비중이 높아 안정 구간에서 deterministic-first 운용이 필요합니다.
- `TOOL_SPECS_VALIDATE_ON_STARTUP=true`: 초기 검증/구성 점검을 강화해 인증 관련 실패를 조기 탐지하세요.

## Gate Reasons
- fallback_rate_above_target: 0.357 > 0.100
- autonomous_success_over_attempt_below_target: 0.611 < 0.700
