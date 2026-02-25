# Agent Quality Report

- sample size: 30 (min required: 20)
- autonomous success rate: 100.0% (29/29, target >= 80.0%)
- autonomous attempt rate: 100.0% (30/30)
- autonomous success over attempts: 96.7% (29/30)
- llm planner failed rate: 0.0% (0/30, target <= 20.0%)
- verification failed rate: 0.0% (0/30, target <= 25.0%)
- guardrail degrade rate: 0.0% (0/30, target <= 40.0%)
- fallback rate: 10.0% (3/30, target <= 10.0%)
- verdict: PASS

## Plan Source Distribution
- llm: 28
- rule: 2

## Execution Mode Distribution
- autonomous: 29
- rule: 1

## Top Fallback Reasons
- replan_limit: 3

## Tuning Hints
- replan_limit 비중이 높습니다. replan 조건을 줄이고 초기 tool ranking 품질을 먼저 개선하세요.

## Policy Recommendations
- `LLM_AUTONOMOUS_REPLAN_LIMIT=2`: replan_limit 비중이 높아 재계획 허용 횟수 상향이 필요합니다.
