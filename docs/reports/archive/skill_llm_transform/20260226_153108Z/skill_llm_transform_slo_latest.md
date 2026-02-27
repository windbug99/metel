# Agent Quality Report

- sample size: 100 (min required: 30)
- autonomous success rate: 0.0% (0/0, target >= 80.0%)
- autonomous attempt rate: 20.0% (20/100)
- autonomous success over attempts: 0.0% (0/20)
- llm planner failed rate: 0.0% (0/100, target <= 20.0%)
- verification failed rate: 0.0% (0/100, target <= 25.0%)
- guardrail degrade rate: 0.0% (0/100, target <= 40.0%)
- fallback rate: 20.0% (20/100, target <= 10.0%)
- verdict: FAIL

## Plan Source Distribution
- dag_template: 90
- rule_recent_lookup: 10

## Execution Mode Distribution
- rule: 100

## Top Fallback Reasons
- TOOL_TIMEOUT: 20

## Top Error Codes
- TOOL_TIMEOUT: 20

## Gate Reasons
- autonomous_success_rate_below_target: 0.000 < 0.800
- fallback_rate_above_target: 0.200 > 0.100
- autonomous_attempt_rate_below_target: 0.200 < 0.500
- autonomous_success_over_attempt_below_target: 0.000 < 0.700
