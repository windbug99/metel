# metel.ai: Direct API 연동 vs MCP 연동 비교 정리

> 비교 대상  
> - **Direct API**: 에이전트(또는 metel)가 각 서비스의 개별 API를 직접 연동/호출  
> - **MCP**: 각 서비스가 MCP 서버(커넥터)로 표준화된 인터페이스를 제공하고, 에이전트는 MCP만 연동

---

## 결론(권장 방향): 하이브리드가 가장 현실적

- **핵심 연동(Core Integrations)**: Direct API로 **깊게**(성능/안정성/특수 기능/디버깅/운영 품질 책임)
- **롱테일 연동(Long-tail Integrations)**: MCP로 **넓게**(연동 폭·속도·생태계 활용)
- 내부 표준(`tool_specs` + `adapter` + `guide`)을 **MCP tool schema로 매핑 가능**하게 설계하면,
  - 내부 Direct API 도구도 MCP처럼 취급 가능
  - 외부 MCP 서버도 동일한 “툴”로 취급 가능  
  → 결과적으로 **Planner/Executor 루프는 유지**하면서 툴 레지스트리만 플러그형으로 확장 가능

---

## 1) 범용성(확장성) 비교: MCP가 더 유리

### Direct API
- 서비스마다 인증(OAuth), 레이트리밋, 페이지네이션, 에러 규격이 달라 **연동 1개 추가 비용이 큼**
- 대신 “그 서비스에서만 가능한 특수 기능”까지 **깊게 파기 쉬움**

### MCP
- 에이전트(클라이언트)가 **MCP 프로토콜을 한 번 구현**하면, MCP 서버(서비스/커넥터)를 **플러그인처럼** 붙일 수 있음
- 많은 서비스(롱테일)를 빠르게 붙이는 데 유리

**정리:** “연동 폭을 넓히는 범용성”은 MCP가 우세.

---

## 2) 효율(개발/운영/성능) 비교: 개발 효율은 MCP, 실행 최적화는 Direct API

### A. 개발/유지보수 효율
- **MCP 유리**
  - 연동을 “표준 서버/커넥터”로 외부화하면, 앱(에이전트)은 “도구 호출”만 하면 됨
  - N(모델/에이전트) × M(툴) 통합에서 중복을 줄이기 쉬움
  - 단, **검증된 품질 기준을 만족한 MCP 커넥터**를 사용한다는 전제가 필요
- **Direct API**
  - 연동 증가에 따라 구현/테스트/운영 표면이 커짐
  - 다만 핵심 연동을 직접 제어할 수 있어 품질 튜닝은 쉬움

### B. 실행 성능/비용/예측가능성(디버깅)
- **Direct API 유리**
  - 호출 경로가 단순 → 레이턴시, 리트라이, 캐싱, 배치 최적화가 쉬움
  - SLA/에러 패턴/관측성(Observability) 확보가 쉬움
- **MCP**
  - 중간 계층(서버/권한/스키마 변환/툴 탐색)이 생겨 운영 구성요소·장애 지점이 늘 수 있음
  - “표준”이라도 MCP 서버 구현 품질에 따라 안정성이 좌우됨

### C. 보안/권한
- 두 방식 모두 **최소 권한(Least privilege)**, **허용 도구 표면 최소화**, **감사 로그(Audit log)**가 핵심
- MCP는 “표준 커넥터”를 쓰더라도 서버 측 구현/배포/업데이트 체인이 추가되므로,
  - 서명된 배포/버전 고정/권한 스코프/샌드박싱/요청 검증이 중요

**정리:**  
- “연동을 많이 붙이고 유지보수”는 MCP가 효율적  
- “핵심 기능의 성능/안정성/최적화/디버깅”은 Direct API가 효율적

---

## 3) 시장성(채택/세일즈) 비교: MCP는 성장세, ‘신뢰/운영’이 승부처

- MCP 지원은 점점 **제품 경쟁력/세일즈 포인트**가 될 가능성이 큼(특히 B2B)
- 다만 기업 고객은 “표준 지원”만큼이나
  - 권한 통제, 감사 로그, 데이터 경계, 장애 대응 체계 등 **운영 신뢰성**을 더 크게 봄
- 따라서 “MCP 지원 + 핵심 연동의 Direct API 고품질” 조합이 가장 설득력 있음

---

## metel.ai 적용 전략(권장)

### 1) Core Integrations (상위 5~10개): Direct API로 깊게
- 예: Google/Notion/Slack/GitHub 등 유료 전환·핵심 워크플로를 만드는 연동
- 목표:
  - 성능(저지연), 안정성(재시도/멱등성), 에러 복구
  - 관측성(트레이싱/로그/메트릭) + 감사 로그
  - 서비스별 “특수 기능”까지 커버

### 2) Long-tail Integrations: MCP로 넓게
- MCP 커넥터/서버를 통해 연동 폭을 빠르게 확장
- 파트너/커뮤니티 연동을 수용해 “연동 갯수”를 경쟁력으로 만들기 좋음

### 3) 내부 표준을 MCP에 매핑 가능한 형태로
- `tool_specs`(기계 스펙) / `adapter`(실 호출) / `guide`(행동 지침)를 유지하되,
- **MCP tool schema ↔ metel tool spec** 변환 계층을 둬서
  - 내부 Direct API 도구도 동일한 tool registry에서 취급
  - 외부 MCP 서버도 동일한 tool registry에서 취급
- 결과: Planner/Executor/Memory 등 핵심 에이전트 로직은 유지하면서 **툴만 플러그형**으로 확장
- 구현 원칙:
  - **단일 내부 adapter를 source of truth로 유지**하고 Direct/MCP 노출은 이 adapter를 통해서만 수행
  - 외부 MCP 서버 호출도 내부 adapter normalization layer를 반드시 통과
  - 동일 기능의 이중 구현(Direct 전용 + MCP 전용 비즈니스 로직) 금지

### 4) 운영 가드레일(필수)
- 하이브리드 구조의 핵심은 “연동 방식”보다 “실행 정책의 일관성”
- Direct API / MCP 모두 동일한 통제면에서 실행되어야 운영 신뢰성 확보 가능

#### A. Tool Tier 정책
- `Tier 1 (Core)` / `Tier 2` / `Tier 3 (Long-tail/MCP)`로 툴 등급화
- 등급별로 다른 실행 정책 적용:
  - 승인 정책(자동/조건부/수동)
  - timeout/retry/circuit breaker 한도
  - observability 샘플링/로그 보존 기간

#### B. 실패 처리와 폴백
- MCP 호출 실패 시나리오를 표준화:
  - 대체 경로(Direct API 또는 기능 축소 응답)
  - 재시도 횟수/백오프/중단 조건
  - 사용자 노출 메시지 규격(무응답/부분 실패/완전 실패)
- “실패했지만 성공처럼 보이는” 상태를 금지하고, 부분 실패를 명시적으로 기록

#### C. 성능/비용 예산 관리
- 툴 레지스트리에 SLO/예산 메타데이터를 필수화:
  - `p95 latency`, `error rate`, `cost per call`, `daily budget`
- Planner가 툴 선택 시 성능/비용 예산을 고려하도록 정책화
- 예산 초과 시 우선순위 규칙:
  - 1순위: 대체 툴 사용
  - 2순위: 기능 축소 실행
  - 3순위: 호출 차단 및 사용자 고지
- Tier 예외:
  - `Tier 1(Core)`은 기본적으로 호출 차단 금지(강한 경보 + 대체/축소 우선)
  - `Tier 2/3`은 예산 정책에 따라 호출 차단 허용

#### D. 배포/버전 통제
- MCP 커넥터는 “버전 고정(pin)” + “검증된 버전만 승격” 원칙 적용
- 릴리즈 채널 분리:
  - canary(내부) → staged(일부 테넌트) → general(전체)
- 서명/무결성 검증, 권한 스코프 검토, 롤백 절차를 릴리즈 체크리스트에 포함

### 5) Core vs Long-tail 분류 매트릭스(정량 기준)
- 분류는 감이 아니라 점수 기반으로 결정(월 1회 재평가)
- 예시 기준:
  - `월 호출량`: 높음(3점) / 중간(2점) / 낮음(1점)
  - `매출/전환 기여`: 높음(3점) / 중간(2점) / 낮음(1점)
  - `장애 민감도`: 높음(3점) / 중간(2점) / 낮음(1점)
  - `특수 기능 필요도`: 높음(3점) / 중간(2점) / 낮음(1점)
  - `보안/컴플라이언스 등급`: 높음(3점) / 중간(2점) / 낮음(1점)
- 권장 규칙:
  - 총점 12점 이상 또는 `장애 민감도=높음`이면 Core(Direct 우선)
  - 총점 11점 이하이면 Long-tail(MCP 우선)
- 플래핑 방지 규칙(hysteresis):
  - 승격: 상위 조건 2회(2개월) 연속 충족 시 적용
  - 강등: 하위 조건 2회(2개월) 연속 충족 시 적용

### 6) 마이그레이션 로드맵(단계/Exit Criteria)
- `Phase 0: PoC`
  - 목표: MCP 1~2개 커넥터 연결, 최소 툴 실행 성공
  - 종료 기준(예시):
    - 성공률 `>= 95%`
    - `p95 latency <= 3000ms`
    - 실패 유형(인증/권한/타임아웃) 분류 가능
    - 월 예상비용 추정 가능
- `Phase 1: 병행 운영`
  - 목표: Core는 Direct 유지, Long-tail 일부를 MCP로 전환
  - 종료 기준(예시):
    - 성공률 `>= 99%`
    - `p95 latency <= 1500ms`
    - `error rate <= 1%`
    - 장애 시 폴백 성공률 `>= 95%`
- `Phase 2: 정책 고도화`
  - 목표: Tier 정책, 예산 제어, 폴백 정책 자동화
  - 종료 기준(예시):
    - 예산 초과 시 정책(대체/축소/차단) 자동 실행율 `>= 99%`
    - 장애 감지~알림 전파 `<= 5분`
    - 운영자 수동介入 없는 복구율 `>= 80%`
- `Phase 3: 확장/정리`
  - 목표: 저효율 직접 연동 정리, 검증된 MCP 확장
  - 종료 기준(예시):
    - 동일 트래픽 대비 운영비 `>= 20%` 절감 또는
    - 동일 비용 대비 성공률/지연 지표 유의미 개선
    - 정리 대상 연동의 기능 회귀 0건

### 7) 테스트/품질 보증 체계(필수)
- 툴 단위 계약 테스트(입출력 스키마, 권한, 에러 코드)
- 통합 회귀 테스트(핵심 사용자 시나리오 기준)
- 장애 주입 테스트(타임아웃, 429, 5xx, 부분 응답)
- 커넥터 인증 체크리스트:
  - 기본 SLO 충족
  - 감사 로그/트레이스 연동
  - 권한 스코프 최소화 검증

### 8) 벤더 종속성 대응(필수)
- 특정 MCP 커넥터 중단/가격 인상/품질 저하를 가정한 대체 전략 준비
- 최소 1개 대체 경로 유지:
  - 대체 MCP 커넥터
  - Direct API 우회 경로
  - 기능 축소 모드
- 계약/운영 관점:
  - 버전/가격 변경 모니터링
  - 중요 커넥터는 교체 리허설 분기별 1회

### 9) 프로토타이핑 단계에서의 최소 필수 항목
- 아래 4개만 우선 필수로 적용:
  - 경량 분류 기준(Core vs Long-tail)
  - 최소 폴백 정책(실패 시 대체/고지)
  - 기본 데이터 경계(테넌트 분리 + 민감 로그 마스킹)
  - 신규 툴 온보딩 체크리스트(간단 버전)
- RACI, 정교한 거버넌스, 장기 보존 정책은 정식 운영 단계에서 확장

### 10) 시장성 주장 근거화 방식
- “MCP 성장세”는 정성 주장에 그치지 않고 내부 지표로 검증:
  - 세일즈 콜에서 MCP 요구 비율
  - POC 승률/기간 변화
  - 경쟁사 대비 연동 커버리지
- 분기별로 업데이트하여 전략 문서에 반영

### 11) 배포 모델 선택 기준(자체 vs 외부 vs 혼합)
- 권장 기본값: **혼합형**
  - Core: Direct API(또는 자체 MCP)로 통제
  - Long-tail: 외부 MCP 서버 활용
- 프로토타입 단계 기본값: **외부 MCP 우선**
  - 목적: 초기 구축 속도 확보, 운영 부담 최소화
- 자체 MCP 전환 트리거:
  - 월 호출량 급증
  - 높은 장애 민감도/강한 SLA 요구
  - 보안/컴플라이언스 요구 강화

### 12) 외부 MCP 서버 선정 우선순위(무료, 안정성)
- 단계별 우선순위:
  - `PoC/프로토타입`: 1순위 무료, 2순위 안정성
  - `정식 운영`: 1순위 안정성, 2순위 총비용(TCO, free tier는 가산점)
- 공통 평가 항목:
  - 3순위: 권한 모델 명확성(OAuth, scope 최소화)
  - 4순위: 버전 관리/변경 공지 체계
  - 5순위: 폴백 가능성(대체 서버/Direct 우회)
- 탈락 기준:
  - 무료 구간 부재 또는 비용 구조 불명확
  - 상태 페이지/장애 공지/버전 정책 부재
  - 감사 로그/추적 연동 어려움

### 13) 외부 MCP 서버 Shortlist 운영안(초기)
- 원칙: 서비스 제공사(1st-party) 또는 검증된 운영 주체 우선
- 후보군 선정 방식:
  - Core 업무와 직접 연결되는 서비스 먼저
  - 무료 검증이 가능한 서버부터 PoC 진행
  - 커넥터별 2주 관측 후 채택/제외 결정
- 채택 게이트(최소):
  - 성공률, p95 지연, 에러율, 월 예상비용 기록
  - 장애 시 대체 경로(다른 MCP 또는 Direct) 확인
  - 권한 스코프/민감 데이터 처리 점검 완료

### 14) KPI 대시보드(지표/수식/알람 임계값)
- 운영/전략 의사결정은 아래 KPI를 단일 대시보드로 추적

| 지표 이름 | 수식(정의) | 알람 임계값 |
|---|---|---|
| Tool Success Rate | `성공 호출 수 / 전체 호출 수 * 100` | `Tier 1 < 99.0%` (5분), `Tier 2/3 < 97.0%` |
| Tool Error Rate | `오류 호출 수(4xx,5xx,timeout) / 전체 호출 수 * 100` | `> 1.0%` (Tier 1), `> 3.0%` (Tier 2/3) |
| p95 Latency | `최근 15분 호출 지연시간의 95퍼센타일` | `Tier 1 > 1500ms`, `Tier 2/3 > 3000ms` |
| Fallback Success Rate | `폴백 성공 수 / 폴백 시도 수 * 100` | `< 95.0%` |
| Budget Burn Rate (일) | `금일 누적 비용 / 일일 예산 * 100` | `> 80%` 경고, `> 100%` 치명 |
| Cost Per Successful Call | `총 호출 비용 / 성공 호출 수` | 주간 평균 대비 `+30%` 초과 |
| Tier 1 Blocked Calls | `정책에 의해 차단된 Tier 1 호출 수` | `> 0` 즉시 알람 |
| MTTR (툴 장애) | `복구 완료 시각 - 장애 감지 시각` 평균 | `> 30분` |
| Connector Change Failure Rate | `릴리즈 후 장애 유발 변경 수 / 전체 변경 수 * 100` | `> 10%` |
| Reclassification Churn | `월간 Core↔Long-tail 재분류 건수 / 전체 툴 수 * 100` | `> 15%` (플래핑 의심) |

#### KPI 운영 규칙(간단)
- 집계 주기: 실시간(1~5분) + 일간 리포트 + 주간 리뷰
- 알람 채널: 운영 채널(경고), 온콜(치명)
- 예외 처리: 배포 윈도우/실험 트래픽은 별도 태그로 분리 집계

### 15) 구현용 메트릭 스키마(최소)
- 현재 `command_logs`는 KPI 계산에 필요한 필드가 일부 부족하므로 최소 확장 권장
- 원칙: 기존 `command_logs` 유지 + KPI 전용 컬럼 추가(파싱 기반 `detail` 의존도 축소)

#### A. command_logs 추가 컬럼(권장)
- `tool_name text null`
- `tool_tier text null` (`tier1`, `tier2`, `tier3`)
- `provider_type text null` (`direct`, `mcp`)
- `latency_ms integer null`
- `is_fallback boolean not null default false`
- `fallback_ok boolean null`
- `cost_usd numeric(12,6) null`
- `blocked_by_policy boolean not null default false`
- `release_channel text null` (`canary`, `staged`, `general`)
- `deployment_version text null`

#### B. 마이그레이션 SQL 예시
```sql
alter table public.command_logs
  add column if not exists tool_name text,
  add column if not exists tool_tier text,
  add column if not exists provider_type text,
  add column if not exists latency_ms integer,
  add column if not exists is_fallback boolean not null default false,
  add column if not exists fallback_ok boolean,
  add column if not exists cost_usd numeric(12,6),
  add column if not exists blocked_by_policy boolean not null default false,
  add column if not exists release_channel text,
  add column if not exists deployment_version text;

create index if not exists idx_command_logs_created_at on public.command_logs (created_at desc);
create index if not exists idx_command_logs_tool_name_created_at on public.command_logs (tool_name, created_at desc);
create index if not exists idx_command_logs_tier_created_at on public.command_logs (tool_tier, created_at desc);
create index if not exists idx_command_logs_provider_created_at on public.command_logs (provider_type, created_at desc);
```

### 16) KPI SQL 쿼리 템플릿(PostgreSQL)
- 시간 윈도우 기본값: 최근 15분(`now() - interval '15 minutes'`)
- 필요 시 `tool_tier`, `provider_type`, `tool_name` 필터로 분리

#### A. Success/Error Rate
```sql
select
  round(100.0 * avg(case when status = 'success' then 1 else 0 end), 2) as success_rate_pct,
  round(100.0 * avg(case when status = 'error' then 1 else 0 end), 2) as error_rate_pct
from public.command_logs
where created_at >= now() - interval '15 minutes';
```

#### B. p95 Latency
```sql
select
  percentile_cont(0.95) within group (order by latency_ms) as p95_latency_ms
from public.command_logs
where created_at >= now() - interval '15 minutes'
  and latency_ms is not null;
```

#### C. Fallback Success Rate
```sql
select
  round(
    100.0 * avg(case when fallback_ok is true then 1 else 0 end),
    2
  ) as fallback_success_rate_pct
from public.command_logs
where created_at >= now() - interval '15 minutes'
  and is_fallback = true;
```

#### D. Budget Burn Rate(일)
```sql
select
  coalesce(sum(cost_usd), 0) as cost_today_usd,
  round(100.0 * coalesce(sum(cost_usd), 0) / nullif(:daily_budget_usd, 0), 2) as burn_rate_pct
from public.command_logs
where created_at >= date_trunc('day', now());
```

#### E. Tier 1 Blocked Calls
```sql
select count(*) as blocked_tier1_calls
from public.command_logs
where created_at >= now() - interval '15 minutes'
  and tool_tier = 'tier1'
  and blocked_by_policy = true;
```

#### F. MTTR(장애 복구 시간, 분)
```sql
with marks as (
  select
    created_at,
    case when status = 'error' then 1 else 0 end as is_error
  from public.command_logs
  where created_at >= now() - interval '7 days'
),
failure_windows as (
  select
    min(created_at) filter (where is_error = 1) as fail_at,
    min(created_at) filter (where is_error = 0) as recover_at
  from marks
)
select
  extract(epoch from (recover_at - fail_at)) / 60.0 as mttr_minutes
from failure_windows
where fail_at is not null and recover_at is not null;
```

### 17) Slack 알람 룰(운영 적용 템플릿)
- 채널:
  - `#metel-ops-alert`: warning
  - `#metel-oncall`: critical
- 정책:
  - `warning`은 2회 연속 윈도우 초과 시 발송
  - `critical`은 1회 초과 즉시 발송
- 알람 메시지 필수 필드:
  - metric, current_value, threshold, window, tool_tier, provider_type, top_affected_tools, runbook_url

#### 예시 룰
- `Tier 1 success_rate < 99.0% (15분)` -> critical
- `Tier 1 p95_latency > 1500ms (15분)` -> warning
- `fallback_success_rate < 95% (15분)` -> warning
- `budget_burn_rate > 80% (일)` -> warning
- `budget_burn_rate > 100% (일)` -> critical
- `blocked_tier1_calls > 0` -> critical

#### Slack Payload 예시(JSON)
```json
{
  "channel": "#metel-oncall",
  "text": "[CRITICAL] Tier1 success_rate breach",
  "blocks": [
    {"type":"section","text":{"type":"mrkdwn","text":"*Metric*: tier1_success_rate\n*Value*: 98.4%\n*Threshold*: <99.0%\n*Window*: 15m"}},
    {"type":"section","text":{"type":"mrkdwn","text":"*Provider*: mcp\n*Top tools*: notion_query_data_source, linear_update_issue"}},
    {"type":"section","text":{"type":"mrkdwn","text":"*Runbook*: https://<internal>/runbooks/mcp-alerts"}}
  ]
}
```

---

## 한 줄 요약
- **범용성/확장 속도/생태계 활용**: MCP  
- **핵심 기능 품질(성능/안정성/디버깅/최적화)**: Direct API  
- **제품 전략**: Core는 Direct API, Long-tail은 MCP, 둘을 같은 “툴 레지스트리”로 통합하는 하이브리드
