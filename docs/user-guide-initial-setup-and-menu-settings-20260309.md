# metel User Guide (Draft)

작성일: 2026-03-09  
대상: metel Dashboard v2 신규 사용자

## 1. 목적
이 문서는 metel을 처음 사용하는 사용자가 아래 두 가지를 빠르게 완료할 수 있도록 돕습니다.
- 초기 설정(First-time Setup)
- 메뉴별 주요 설정 방법

## 2. 시작 전 체크
- 계정 로그인 상태 확인
- 소속 Organization / Team 접근 권한 확인
- `scope` 기준 확인
  - `User`: 내 계정 기준 화면
  - `Organization`: 조직 기준 관리 화면
  - `Team`: 팀 기준 운영 화면

## 3. 초기 설정 (Step by Step)

### Step 1. 프로필 확인
경로: `User > Profile`
1. 사용자명/표시 정보 확인
2. 필요한 경우 기본 프로필 값 업데이트
3. 알림/기본 사용 환경 관련 설정이 있으면 우선 반영

완료 기준
- 본인 계정 식별 정보가 정확함

### Step 2. 보안 설정
경로: `User > Security`
1. 비밀번호 정책 확인 및 변경(필요 시)
2. 2차 인증(지원 시) 활성화
3. 최근 보안 이벤트/세션 상태 점검

완료 기준
- 최소 보안 요구사항 충족

### Step 3. OAuth 연결
경로: `User > OAuth Connections`
1. 업무에 필요한 Provider(예: Notion, Linear, Spotify) 연결
2. 연결 상태(Connected/Disconnected) 확인
3. 권한 범위(scope) 점검
4. 불필요한 연결은 해제

완료 기준
- 필수 Provider 연결 완료

### Step 4. 팀 정책/멤버십 확인
경로: `Team > Team Policy`
1. 본인이 속한 Team 확인
2. Team 정책 제한사항(허용 도구/액션) 확인
3. 본인 역할(member/admin/owner)에서 가능한 작업 범위 확인

완료 기준
- 팀 운영 정책 이해 및 작업 가능 범위 파악

### Step 5. API Key 준비(필요 사용자)
경로: `Team > API Keys`
1. 사용 목적별 키 이름으로 생성
2. 허용 도구/정책 범위 최소권한으로 설정
3. 키 발급 직후 안전한 저장소에 보관
4. 테스트 호출 후 정상 동작 확인

완료 기준
- 최소권한 API Key 1개 이상 정상 발급

### Step 6. 사용량/감사 로그 확인
경로:
- `Team > Usage`
- `Team > Audit Events`
1. 최근 호출량/실패율 확인
2. 비정상 호출 또는 권한 거부 이벤트 확인
3. 필요한 경우 관리자에게 정책 변경 요청

완료 기준
- 운영 이상 징후 점검 루틴 확보

## 4. 메뉴별 설정 가이드

### 4.1 Organization 메뉴

#### Organizations
경로: `Organization > Organizations`
- 조직 생성/조회
- 멤버 초대 및 역할 변경
- Role Request 승인/거절

설정 팁
- 운영자 권한(owner/admin) 사용자만 변경 작업 수행
- 역할 변경은 Audit 관점에서 사유를 남길 것

#### Integrations
경로: `Organization > Integrations`
- 조직 단위 Webhook 엔드포인트 등록
- 이벤트 타입별 전송 여부 점검

설정 팁
- 운영/개발 엔드포인트 분리
- Secret/서명 검증 로직 필수 적용

#### OAuth Governance
경로: `Organization > OAuth Governance`
- 조직 허용 Provider 목록 관리
- 필수 연결 Provider 정책 적용
- 구성원 연결 상태를 정책 기준으로 점검

설정 팁
- 필수 Provider를 최소화해 초기 진입 장벽 낮추기
- 정책 변경 전 팀별 영향도 확인

#### Audit Settings
경로: `Organization > Audit Settings`
- 감사 로그 보존 정책 설정
- 민감 이벤트 로깅 수준 설정

설정 팁
- 보안/컴플라이언스 요구 수준에 맞춰 보존기간 결정

#### Admin / Ops
경로: `Organization > Admin / Ops`
- 운영자용 점검/운영 기능 사용
- 장애 대응 또는 운영 작업 실행

설정 팁
- 운영 명령 실행 전 영향 범위 확인
- 실행 기록과 승인 절차를 일관되게 유지

### 4.2 Team 메뉴

#### Overview
경로: `Team > Overview`
- 팀 기준 핵심 지표(KPI) 확인
- 이상 징후(급증/급감) 빠른 탐지

#### Usage
경로: `Team > Usage`
- 도구별 호출량/실패율/지연시간 확인
- 기간 필터(예: 24h, 7d) 기반 비교

#### Team Policy
경로: `Team > Team Policy`
- 팀 정책 작성/수정
- Organization baseline 위반 여부 검증

설정 팁
- 정책 변경은 작은 단위로 나눠 점진 반영

#### Agent Guide
경로: `Team > Agent Guide`
- JSON-RPC 예제 확인
- `list_tools`, `call_tool` 호출 샘플 복사

#### API Keys
경로: `Team > API Keys`
- 키 생성/회전/폐기
- 도구 허용 목록, 만료, 상태 관리

설정 팁
- 키 유출 대응을 위해 정기 회전 주기 운영

#### Policy Simulator
경로: `Team > Policy Simulator`
- 정책 적용 결과 사전 시뮬레이션
- 배포 전 허용/차단 동작 검증

#### Audit Events
경로: `Team > Audit Events`
- 팀 단위 이벤트 추적
- 사용자/도구/시간 기준 필터링

### 4.3 User 메뉴

#### My Requests
경로: `User > My Requests`
- 본인 요청 이력 조회
- 요청 상태(대기/완료/거절) 확인

#### Security
경로: `User > Security`
- 계정 보안 설정 관리
- 인증/세션 관련 정보 점검

#### OAuth Connections
경로: `User > OAuth Connections`
- 개인 연결 관리(연결/해제/상태 확인)

## 5. 운영 권장 순서
1. User 기본 설정(Profile/Security/OAuth)
2. Team 운영 설정(Team Policy/API Keys)
3. Team 검증(Usage/Audit/Simulator)
4. Organization 거버넌스 적용(OAuth Governance/Audit Settings)

## 6. 자주 발생하는 문제

### Q1. 메뉴가 안 보입니다.
- 원인: 역할/권한 부족 가능성
- 조치: 관리자에게 role 및 scope 확인 요청

### Q2. Team 화면에서 데이터가 비어 있습니다.
- 원인: `scope=team`에 필요한 `org/team` 파라미터 누락
- 조치: 조직/팀 선택 후 다시 접근

### Q3. OAuth 연결 후에도 도구 호출이 실패합니다.
- 원인: Organization 정책에서 provider 미허용 또는 필수 조건 불충족
- 조치: `Organization > OAuth Governance` 정책 확인

## 7. 문서 적용 범위
- 이 문서는 온보딩용 초안이며, 실제 화면/정책 변경 시 즉시 업데이트해야 합니다.
- 다음 단계에서 본 문서를 기준으로 대시보드 본문 `User Guide` 페이지 렌더링을 구현합니다.
