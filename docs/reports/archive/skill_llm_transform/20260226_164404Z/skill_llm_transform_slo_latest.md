# Agent Quality Report

- sample size: 40 (min required: 30)
- autonomous success rate: 0.0% (0/0, target >= 80.0%)
- autonomous attempt rate: 25.0% (10/40)
- autonomous success over attempts: 0.0% (0/10)
- llm planner failed rate: 0.0% (0/40, target <= 20.0%)
- verification failed rate: 0.0% (0/40, target <= 25.0%)
- guardrail degrade rate: 0.0% (0/40, target <= 40.0%)
- fallback rate: 25.0% (10/40, target <= 10.0%)
- verdict: FAIL

## Plan Source Distribution
- llm: 30
- calendar_linear_template: 10

## Execution Mode Distribution
- rule: 40

## Top Fallback Reasons
- validation_error: 10

## Top Error Codes
- validation_error: 10

## Gate Reasons
- autonomous_success_rate_below_target: 0.000 < 0.800
- fallback_rate_above_target: 0.250 > 0.100
- autonomous_attempt_rate_below_target: 0.250 < 0.500
- autonomous_success_over_attempt_below_target: 0.000 < 0.700
