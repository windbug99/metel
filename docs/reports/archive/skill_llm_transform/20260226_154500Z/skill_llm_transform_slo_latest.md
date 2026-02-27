# Agent Quality Report

- sample size: 122 (min required: 30)
- autonomous success rate: 0.0% (0/0, target >= 80.0%)
- autonomous attempt rate: 21.3% (26/122)
- autonomous success over attempts: 0.0% (0/26)
- llm planner failed rate: 0.0% (0/122, target <= 20.0%)
- verification failed rate: 0.0% (0/122, target <= 25.0%)
- guardrail degrade rate: 0.0% (0/122, target <= 40.0%)
- fallback rate: 21.3% (26/122, target <= 10.0%)
- verdict: FAIL

## Plan Source Distribution
- dag_template: 106
- rule_recent_lookup: 10
- llm: 6

## Execution Mode Distribution
- rule: 122

## Top Fallback Reasons
- TOOL_TIMEOUT: 20
- auth_error: 6

## Top Error Codes
- TOOL_TIMEOUT: 20
- auth_error: 6

## Policy Recommendations
- `TOOL_SPECS_VALIDATE_ON_STARTUP=true`: 초기 검증/구성 점검을 강화해 인증 관련 실패를 조기 탐지하세요.

## Gate Reasons
- autonomous_success_rate_below_target: 0.000 < 0.800
- fallback_rate_above_target: 0.213 > 0.100
- autonomous_attempt_rate_below_target: 0.213 < 0.500
- autonomous_success_over_attempt_below_target: 0.000 < 0.700
