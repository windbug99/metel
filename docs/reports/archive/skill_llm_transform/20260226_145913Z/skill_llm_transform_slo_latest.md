# Agent Quality Report

- sample size: 40 (min required: 30)
- autonomous success rate: 0.0% (0/0, target >= 80.0%)
- autonomous attempt rate: 50.0% (20/40)
- autonomous success over attempts: 0.0% (0/20)
- llm planner failed rate: 0.0% (0/40, target <= 20.0%)
- verification failed rate: 0.0% (0/40, target <= 25.0%)
- guardrail degrade rate: 0.0% (0/40, target <= 40.0%)
- fallback rate: 50.0% (20/40, target <= 10.0%)
- verdict: FAIL

## Plan Source Distribution
- dag_template: 40

## Execution Mode Distribution
- rule: 40

## Top Fallback Reasons
- TOOL_TIMEOUT: 20

## Top Error Codes
- TOOL_TIMEOUT: 20

## Gate Reasons
- autonomous_success_rate_below_target: 0.000 < 0.800
- fallback_rate_above_target: 0.500 > 0.100
- autonomous_success_over_attempt_below_target: 0.000 < 0.700
