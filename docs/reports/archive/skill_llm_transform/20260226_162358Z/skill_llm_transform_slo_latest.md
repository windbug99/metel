# Agent Quality Report

- sample size: 20 (min required: 30)
- autonomous success rate: 0.0% (0/0, target >= 80.0%)
- autonomous attempt rate: 25.0% (5/20)
- autonomous success over attempts: 0.0% (0/5)
- llm planner failed rate: 0.0% (0/20, target <= 20.0%)
- verification failed rate: 0.0% (0/20, target <= 25.0%)
- guardrail degrade rate: 0.0% (0/20, target <= 40.0%)
- fallback rate: 25.0% (5/20, target <= 10.0%)
- verdict: FAIL

## Plan Source Distribution
- llm: 15
- calendar_linear_template: 5

## Execution Mode Distribution
- rule: 20

## Top Fallback Reasons
- validation_error: 5

## Top Error Codes
- validation_error: 5

## Gate Reasons
- insufficient_sample: 20 < 30
