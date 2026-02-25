# Agent Quality Report

- sample size: 30 (min required: 20)
- autonomous success rate: 92.9% (26/28, target >= 80.0%)
- autonomous attempt rate: 93.3% (28/30)
- autonomous success over attempts: 92.9% (26/28)
- llm planner failed rate: 0.0% (0/30, target <= 20.0%)
- verification failed rate: 0.0% (0/30, target <= 25.0%)
- guardrail degrade rate: 0.0% (0/30, target <= 40.0%)
- fallback rate: 26.7% (8/30, target <= 20.0%)
- verdict: FAIL

## Plan Source Distribution
- llm: 19
- rule: 11

## Execution Mode Distribution
- autonomous: 28
- rule: 2

## Top Fallback Reasons
- replan_limit: 8

## Top Error Codes
- replan_limit: 2
- execution_failed: 2

## Tuning Hints
- replan_limit 비중이 높습니다. replan 조건을 줄이고 초기 tool ranking 품질을 먼저 개선하세요.

## Policy Recommendations
- `LLM_AUTONOMOUS_REPLAN_LIMIT=2`: replan_limit 비중이 높아 재계획 허용 횟수 상향이 필요합니다.

## Gate Reasons
- fallback_rate_above_target: 0.267 > 0.200
