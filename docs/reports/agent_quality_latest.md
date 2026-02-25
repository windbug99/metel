# Agent Quality Report

- sample size: 30 (min required: 20)
- autonomous success rate: 0.0% (0/0, target >= 80.0%)
- autonomous attempt rate: 43.3% (13/30)
- autonomous success over attempts: 0.0% (0/13)
- llm planner failed rate: 0.0% (0/30, target <= 20.0%)
- verification failed rate: 0.0% (0/30, target <= 25.0%)
- guardrail degrade rate: 0.0% (0/30, target <= 40.0%)
- fallback rate: 43.3% (13/30, target <= 20.0%)
- verdict: FAIL

## Plan Source Distribution
- router_v2: 17
- rule: 7
- llm: 6

## Execution Mode Distribution
- router_v2: 17
- rule: 13

## Top Fallback Reasons
- llm_unavailable: 6
- auth_error: 3
- calendar_pipeline_failed: 2
- realtime_data_unavailable: 2

## Top Error Codes
- llm_unavailable: 6
- auth_error: 3
- calendar_pipeline_failed: 2
- realtime_data_unavailable: 2

## Policy Recommendations
- `TOOL_SPECS_VALIDATE_ON_STARTUP=true`: 초기 검증/구성 점검을 강화해 인증 관련 실패를 조기 탐지하세요.

## Gate Reasons
- autonomous_success_rate_below_target: 0.000 < 0.800
- fallback_rate_above_target: 0.433 > 0.200
- autonomous_attempt_rate_below_target: 0.433 < 0.500
- autonomous_success_over_attempt_below_target: 0.000 < 0.700
