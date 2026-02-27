# STEPWISE vs 기존 구조 대시보드/리포트 템플릿 (2026-02-27)

## 1) 목적
- 신규 STEPWISE 구조와 기존 구조의 성능/안정성을 동일 기준으로 비교한다.
- 채택 의사결정(유지/롤백/확대)을 주간 리포트 1장으로 가능하게 만든다.

## 2) 데이터 소스
- `public.command_logs`
  - 실행 단위 결과(`final_status`, `error_code`, `failure_reason`, `detail`)
- `public.pipeline_step_logs`
  - 단계 단위 결과(`validation_status`, `call_status`, `missing_required_fields`)

## 3) 모드 분류 규칙
- `stepwise`: `command_logs.detail`의 `pipeline_json` 내부 `router_mode == "STEPWISE_PIPELINE"`
- `dag`: `command_logs.detail`의 `pipeline_json` 내부 `composed_pipeline == true` 이고 `router_mode != "STEPWISE_PIPELINE"`
- `legacy`: 위 두 조건에 해당하지 않는 실행

## 4) 핵심 KPI 정의
- 실행 성공률: `final_status='success' / 전체 실행`
- 검증 실패율: `error_code in ('validation_error','missing_required_fields') / 전체 실행`
- 평균 단계 수: `pipeline_step_logs` 기준 run 단위 step count 평균
- p95 지연: `detail`의 `analysis_latency_ms` p95
- 단계 호출 실패율: `pipeline_step_logs.call_status='failed' / 전체 step`
- 필수값 누락 실패율: `missing_required_fields`가 비어있지 않은 step 비율

## 5) SQL 템플릿

### 5.1 일자별 모드 비교 (성공률/검증실패율/p95)
```sql
with base as (
  select
    date_trunc('day', created_at) as d,
    case
      when detail like '%"router_mode":"STEPWISE_PIPELINE"%' then 'stepwise'
      when detail like '%"composed_pipeline":true%' then 'dag'
      else 'legacy'
    end as mode,
    coalesce(final_status, status) as final_status,
    coalesce(error_code, '') as error_code,
    nullif(substring(detail from 'analysis_latency_ms=([0-9]+)'), '')::int as latency_ms
  from public.command_logs
  where command = 'agent_plan'
    and created_at >= now() - interval '14 days'
)
select
  d::date as date,
  mode,
  count(*) as run_count,
  round(100.0 * avg(case when final_status = 'success' then 1 else 0 end), 2) as success_rate_pct,
  round(
    100.0 * avg(case when error_code in ('validation_error', 'missing_required_fields') then 1 else 0 end),
    2
  ) as validation_fail_rate_pct,
  percentile_cont(0.95) within group (order by latency_ms) as p95_latency_ms
from base
group by d, mode
order by d desc, mode;
```

### 5.2 run 단위 평균 단계 수 / 단계 실패율
```sql
with run_mode as (
  select
    c.run_id,
    c.request_id,
    case
      when c.detail like '%"router_mode":"STEPWISE_PIPELINE"%' then 'stepwise'
      when c.detail like '%"composed_pipeline":true%' then 'dag'
      else 'legacy'
    end as mode
  from public.command_logs c
  where c.command = 'agent_plan'
    and c.created_at >= now() - interval '14 days'
),
step_agg as (
  select
    p.run_id,
    count(*) as step_count,
    sum(case when p.call_status = 'failed' then 1 else 0 end) as failed_steps,
    sum(case when p.validation_status = 'failed' then 1 else 0 end) as validation_failed_steps
  from public.pipeline_step_logs p
  where p.created_at >= now() - interval '14 days'
  group by p.run_id
)
select
  r.mode,
  count(*) as run_count,
  round(avg(coalesce(s.step_count, 0)), 2) as avg_step_count,
  round(100.0 * avg(case when coalesce(s.failed_steps, 0) > 0 then 1 else 0 end), 2) as run_has_failed_step_pct,
  round(100.0 * avg(case when coalesce(s.validation_failed_steps, 0) > 0 then 1 else 0 end), 2) as run_has_validation_failed_step_pct
from run_mode r
left join step_agg s on s.run_id = r.run_id
group by r.mode
order by r.mode;
```

### 5.3 STEPWISE 실패 원인 TOP N
```sql
select
  coalesce(failure_reason, 'unknown') as failure_reason,
  count(*) as cnt
from public.command_logs
where command = 'agent_plan'
  and created_at >= now() - interval '14 days'
  and detail like '%"router_mode":"STEPWISE_PIPELINE"%'
  and coalesce(final_status, status) <> 'success'
group by 1
order by cnt desc
limit 20;
```

### 5.4 STEPWISE 단계 품질 (API/검증/필수값누락)
```sql
select
  coalesce(api, 'unknown') as api,
  count(*) as step_count,
  round(100.0 * avg(case when validation_status = 'failed' then 1 else 0 end), 2) as validation_failed_pct,
  round(100.0 * avg(case when call_status = 'failed' then 1 else 0 end), 2) as call_failed_pct,
  round(100.0 * avg(case when jsonb_array_length(missing_required_fields) > 0 then 1 else 0 end), 2) as missing_required_pct
from public.pipeline_step_logs
where created_at >= now() - interval '14 days'
  and task_id like 'step_%'
group by 1
order by step_count desc;
```

## 6) 주간 리포트 템플릿
```md
# STEPWISE 주간 비교 리포트 (YYYY-MM-DD ~ YYYY-MM-DD)

## 1. 요약
- 결론: [유지 / 개선 후 재평가 / 점진 확대 / 롤백]
- 표본 수: 총 N건 (stepwise N건, dag N건, legacy N건)

## 2. KPI 비교
- 성공률: stepwise XX% / dag XX% / legacy XX%
- 검증 실패율: stepwise XX% / dag XX% / legacy XX%
- 평균 단계 수: stepwise X.X / dag X.X
- p95 지연: stepwise XXXms / dag XXXms / legacy XXXms

## 3. STEPWISE 실패 Top 5
1. failure_reason_a (N건, XX%)
2. failure_reason_b (N건, XX%)
3. failure_reason_c (N건, XX%)
4. failure_reason_d (N건, XX%)
5. failure_reason_e (N건, XX%)

## 4. 개선 액션
1. [액션명] - 담당 - ETA
2. [액션명] - 담당 - ETA
3. [액션명] - 담당 - ETA

## 5. 다음 주 채택 기준
- 성공률 >= 95%
- 사용자 가시 오류율 <= 5%
- p95 지연 증가 <= +10%
```

## 7) 운영 규칙
- 동일 기간/동일 표본 조건으로만 비교한다.
- `run_count < 200`이면 채택 의사결정을 유보한다.
- 리포트는 주 1회 고정 포맷으로 저장한다.
