# Agent Quality Report

- sample size: 30 (min required: 20)
- autonomous success rate: 0.0% (0/0, target >= 80.0%)
- autonomous attempt rate: 0.0% (0/30)
- autonomous success over attempts: 0.0% (0/0)
- llm planner failed rate: 0.0% (0/30, target <= 20.0%)
- verification failed rate: 0.0% (0/30, target <= 25.0%)
- guardrail degrade rate: 0.0% (0/30, target <= 40.0%)
- fallback rate: 0.0% (0/30, target <= 20.0%)
- verdict: FAIL

## Plan Source Distribution
- dag_template: 30

## Execution Mode Distribution
- rule: 30

## Gate Reasons
- autonomous_success_rate_below_target: 0.000 < 0.800
- autonomous_attempt_rate_below_target: 0.000 < 0.500
- autonomous_success_over_attempt_below_target: 0.000 < 0.700
