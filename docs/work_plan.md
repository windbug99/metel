# metel 실행 계획 (Overhaul 동기화본)

기준 문서: `docs/overhaul-20260302.md`

본 문서는 `overhaul`의 실행 항목을 작업 관점으로 재정리한 문서이며,
단계명/체크리스트 용어는 `overhaul`와 동일하게 유지한다.

## 1. Phase 1 — MCP Gateway MVP

목표:
- 5분 안에 AI Agent가 SaaS 호출 가능

범위:
- OAuth 연결
- API Key 발급
- MCP `list_tools`
- MCP `call_tool`
- 스키마 검증
- 기본 rate limit
- 요청 로그 저장

상태:
- 완료 (`overhaul` 기준 체크 완료)

완료 기준:
- AI Agent에서 MCP 연결 성공
- Notion/Linear 호출 성공
- 스키마 에러 표준화
- rate limit 동작
- 로그 저장

## 2. Phase 2 — Safe Execution 강화

목표:
- “AI Safe Gateway”로 포지셔닝 시작

### 1) 정책/안전 기능

- [x] Risk Gate 추가 (삭제/아카이브 등 위험 작업 기본 차단)
- [x] Resolver 추가 (name -> id 보정)
- [x] 표준 에러 코드 체계 확장 (정책 위반/리졸브 실패/외부 API 장애)
- [x] Retry 정책 도입 (일시 실패에 한해 재시도)
- [x] 사용자/키 단위 쿼터 제한 도입

### 2) 운영 안정성

- [x] 장애/실패 유형 대시보드 추가
- [x] 실패율/재시도율/차단율 측정 지표 정의
- [x] 핵심 경로 테스트 보강 (schema/risk/retry/resolver)

### 3) Phase 2 완료 기준

- [x] 위험 작업 사전 차단 동작 확인
- [x] name 기반 입력이 안정적으로 id 보정됨
- [x] 재시도 정책으로 일시 장애 복구율 개선
- [x] 쿼터 초과 동작이 일관되게 처리됨

실행 준비 문서:
- `docs/phase2-prep-20260303.md`

## 3. Phase 3 — Execution Control Platform 전환

목표:
- Enterprise 방향으로 확장

### 1) 권한/통제 확장

- [ ] API Key별 Tool 권한 설정
- [ ] 팀 단위 정책 적용 (허용/차단 규칙)
- [ ] Audit UI 제공
- [ ] Usage Dashboard 제공 (호출수/성공률/실패원인)
- [ ] Webhook/Event Log Export 제공

### 2) 플랫폼 품질

- [ ] 멀티테넌시 격리 검증
- [ ] 운영자용 정책 관리 플로우 정리
- [ ] 감사 추적성(누가/언제/무엇을) 검증

### 3) Phase 3 완료 기준

- [ ] 키/팀 기준으로 실행 권한이 분리됨
- [ ] 조직 단위 감사 및 사용량 분석 가능
- [ ] 외부 SIEM/내부 시스템으로 이벤트 연동 가능

## 4. Phase 4 — Enterprise Layer

목표:
- 진짜 B2B

### 1) 엔터프라이즈 요구사항

- [ ] Organization/Team RBAC 완성
- [ ] 승인 워크플로우(고위험 작업) 도입
- [ ] 정책 DSL 도입
- [ ] SSO(SAML/OIDC) 연동
- [ ] Usage-based billing 도입
- [ ] SOC2 대응 통제 항목 정리 및 증적 수집 체계 구축

### 2) Phase 4 완료 기준

- [ ] 엔터프라이즈 보안/감사 요구사항 충족
- [ ] 조직 규모 확장 시 권한/승인/정책 관리 가능
- [ ] 과금/정산/감사 대응까지 운영 가능

## 5. 우선순위 실행 순서 (권장)

- [x] 1순위: Phase 1 데이터/인증 기반 (`api_keys`, `tool_calls`, 인증 미들웨어)
- [x] 2순위: Phase 1 MCP 라우트 (`list_tools`, `call_tool`)
- [x] 3순위: Phase 1 안전 최소 레이어 (schema/rate limit/error code/logging)
- [x] 4순위: Phase 1 프론트 UI (API Key + 연결 상태)
- [ ] 5순위: Phase 2 핵심 2개 선반영 (Risk Gate, Resolver)

## 6. 동기화 규칙

- 단계명/체크리스트 텍스트는 `docs/overhaul-20260302.md`를 마스터로 사용한다.
- 본 문서 수정 시 `overhaul`와 불일치가 생기면 `overhaul` 기준으로 즉시 맞춘다.
- 레거시 계획(텔레그램/이전 에이전트 중심)은 본 문서에 포함하지 않는다.
