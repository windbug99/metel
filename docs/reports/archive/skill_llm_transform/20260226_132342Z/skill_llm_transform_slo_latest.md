# Agent Quality Report

- sample size: 44 (min required: 30)
- autonomous success rate: 0.0% (0/0, target >= 80.0%)
- autonomous attempt rate: 45.5% (20/44)
- autonomous success over attempts: 0.0% (0/20)
- llm planner failed rate: 0.0% (0/44, target <= 20.0%)
- verification failed rate: 0.0% (0/44, target <= 25.0%)
- guardrail degrade rate: 0.0% (0/44, target <= 40.0%)
- fallback rate: 45.5% (20/44, target <= 10.0%)
- verdict: FAIL

## Plan Source Distribution
- dag_template: 42
- llm: 1
- rule: 1

## Execution Mode Distribution
- rule: 44

## Top Fallback Reasons
- TOOL_TIMEOUT: 20

## Top Error Codes
- TOOL_TIMEOUT: 20

## Gate Reasons
- autonomous_success_rate_below_target: 0.000 < 0.800
- fallback_rate_above_target: 0.455 > 0.100
- autonomous_attempt_rate_below_target: 0.455 < 0.500
- autonomous_success_over_attempt_below_target: 0.000 < 0.700
