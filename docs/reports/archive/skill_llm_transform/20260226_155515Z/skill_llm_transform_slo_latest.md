# Agent Quality Report

- sample size: 87 (min required: 30)
- autonomous success rate: 0.0% (0/0, target >= 80.0%)
- autonomous attempt rate: 11.5% (10/87)
- autonomous success over attempts: 0.0% (0/10)
- llm planner failed rate: 0.0% (0/87, target <= 20.0%)
- verification failed rate: 0.0% (0/87, target <= 25.0%)
- guardrail degrade rate: 0.0% (0/87, target <= 40.0%)
- fallback rate: 11.5% (10/87, target <= 10.0%)
- verdict: FAIL

## Plan Source Distribution
- dag_template: 67
- llm: 10
- rule_recent_lookup: 10

## Execution Mode Distribution
- rule: 87

## Top Fallback Reasons
- auth_error: 10

## Top Error Codes
- auth_error: 10

## Policy Recommendations
- `TOOL_SPECS_VALIDATE_ON_STARTUP=true`: 초기 검증/구성 점검을 강화해 인증 관련 실패를 조기 탐지하세요.

## Gate Reasons
- autonomous_success_rate_below_target: 0.000 < 0.800
- fallback_rate_above_target: 0.115 > 0.100
- autonomous_attempt_rate_below_target: 0.115 < 0.500
- autonomous_success_over_attempt_below_target: 0.000 < 0.700
