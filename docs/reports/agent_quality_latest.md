# Agent Quality Report

- sample size: 30 (min required: 20)
- autonomous success rate: 0.0% (0/0, target >= 80.0%)
- autonomous attempt rate: 63.3% (19/30)
- autonomous success over attempts: 0.0% (0/19)
- llm planner failed rate: 0.0% (0/30, target <= 20.0%)
- verification failed rate: 0.0% (0/30, target <= 25.0%)
- guardrail degrade rate: 0.0% (0/30, target <= 40.0%)
- fallback rate: 63.3% (19/30, target <= 20.0%)
- verdict: FAIL

## Plan Source Distribution
- dag_template: 14
- llm: 9
- rule: 7

## Execution Mode Distribution
- rule: 30

## Top Fallback Reasons
- TOOL_TIMEOUT: 9
- calendar_pipeline_failed: 3
- auth_error: 3
- DSL_REF_NOT_FOUND: 2
- COMPENSATION_FAILED: 1

## Top Error Codes
- TOOL_TIMEOUT: 9
- calendar_pipeline_failed: 3
- auth_error: 3
- DSL_REF_NOT_FOUND: 2
- COMPENSATION_FAILED: 1

## Policy Recommendations
- `TOOL_SPECS_VALIDATE_ON_STARTUP=true`: 초기 검증/구성 점검을 강화해 인증 관련 실패를 조기 탐지하세요.

## Gate Reasons
- autonomous_success_rate_below_target: 0.000 < 0.800
- fallback_rate_above_target: 0.633 > 0.200
- autonomous_success_over_attempt_below_target: 0.000 < 0.700
