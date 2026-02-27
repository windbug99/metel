# Agent Quality Report

- sample size: 41 (min required: 30)
- autonomous success rate: 0.0% (0/0, target >= 80.0%)
- autonomous attempt rate: 2.4% (1/41)
- autonomous success over attempts: 0.0% (0/1)
- llm planner failed rate: 0.0% (0/41, target <= 20.0%)
- verification failed rate: 0.0% (0/41, target <= 25.0%)
- guardrail degrade rate: 0.0% (0/41, target <= 40.0%)
- fallback rate: 2.4% (1/41, target <= 10.0%)
- verdict: FAIL

## Plan Source Distribution
- dag_template: 41

## Execution Mode Distribution
- rule: 41

## Top Fallback Reasons
- TOOL_TIMEOUT: 1

## Top Error Codes
- TOOL_TIMEOUT: 1

## Gate Reasons
- autonomous_success_rate_below_target: 0.000 < 0.800
- autonomous_attempt_rate_below_target: 0.024 < 0.500
- autonomous_success_over_attempt_below_target: 0.000 < 0.700
