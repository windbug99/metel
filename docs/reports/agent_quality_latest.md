# Agent Quality Report

- sample size: 30 (min required: 20)
- autonomous success rate: 88.0% (22/25, target >= 80.0%)
- autonomous attempt rate: 90.0% (27/30)
- autonomous success over attempts: 81.5% (22/27)
- llm planner failed rate: 0.0% (0/30, target <= 20.0%)
- verification failed rate: 0.0% (0/30, target <= 25.0%)
- guardrail degrade rate: 3.3% (1/30, target <= 40.0%)
- fallback rate: 16.7% (5/30, target <= 20.0%)
- verdict: PASS

## Plan Source Distribution
- llm: 17
- rule: 9
- dag_template: 4

## Execution Mode Distribution
- autonomous: 25
- rule: 5

## Top Fallback Reasons
- verification_failed: 2
- TOOL_TIMEOUT: 1
- replan_limit: 1
- tool_error_rate: 1

## Top Error Codes
- replan_limit: 3
- TOOL_TIMEOUT: 1
- auth_error: 1

## Top Guardrail Degrade Reasons
- tool_error_rate: 1

## Tuning Hints
- verification_failed 비중이 높습니다. intent별 완료조건(verifier)을 세분화하고 final 허용 조건을 강화하세요.
- replan_limit 비중이 높습니다. replan 조건을 줄이고 초기 tool ranking 품질을 먼저 개선하세요.
- 도구 오류율 기반 강등이 잦습니다. payload 정규화와 스키마 자동보정 정책을 강화하세요.

## Policy Recommendations
- `LLM_AUTONOMOUS_LIMIT_RETRY_ONCE=true`: 검증 실패 비중이 높아 자동 재시도 정책 유지/활성화가 필요합니다.
- `LLM_AUTONOMOUS_RULE_FALLBACK_MUTATION_ENABLED=false`: mutation 요청은 rule fallback 대신 자율 재시도로 수렴시키는 것이 유리합니다.
- `LLM_AUTONOMOUS_REPLAN_LIMIT=2`: replan_limit 비중이 높아 재계획 허용 횟수 상향이 필요합니다.
- `LLM_HYBRID_EXECUTOR_FIRST=true`: 가드레일 강등 비중이 높아 안정 구간에서 deterministic-first 운용이 필요합니다.
- `TOOL_SPECS_VALIDATE_ON_STARTUP=true`: 초기 검증/구성 점검을 강화해 인증 관련 실패를 조기 탐지하세요.
