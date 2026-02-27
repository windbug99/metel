# Agent Quality Report

- sample size: 71 (min required: 30)
- autonomous success rate: 0.0% (0/0, target >= 80.0%)
- autonomous attempt rate: 1.4% (1/71)
- autonomous success over attempts: 0.0% (0/1)
- llm planner failed rate: 0.0% (0/71, target <= 20.0%)
- verification failed rate: 0.0% (0/71, target <= 25.0%)
- guardrail degrade rate: 0.0% (0/71, target <= 40.0%)
- fallback rate: 1.4% (1/71, target <= 10.0%)
- verdict: FAIL

## Plan Source Distribution
- dag_template: 71

## Execution Mode Distribution
- rule: 71

## Top Fallback Reasons
- TOOL_TIMEOUT: 1

## Top Error Codes
- TOOL_TIMEOUT: 1

## Gate Reasons
- autonomous_success_rate_below_target: 0.000 < 0.800
- autonomous_attempt_rate_below_target: 0.014 < 0.500
- autonomous_success_over_attempt_below_target: 0.000 < 0.700
