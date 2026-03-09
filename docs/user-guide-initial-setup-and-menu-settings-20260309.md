# metel User Guide (v2)

작성일: 2026-03-09  
대상: metel Dashboard v2를 처음 사용하는 사용자(Owner/Admin/Member)

---

## 0. 이 문서의 목적과 사용 순서
이 문서는 metel을 처음 도입할 때 아래 목표를 달성하도록 설계되었습니다.
- 조직(Organization) 생성과 기본 거버넌스 설정
- Admin/Member 초대 및 권한 체계 정립
- 감사(Audit), OAuth, API Key 정책 설정
- 팀(Team) 생성 및 팀 단위 정책/운영 설정
- 사용자(User) 개인 보안/연결 설정

권장 읽기 순서
1. Organization 설정
2. Team 설정
3. User 설정
4. 메뉴별 상세 가이드(Reference)

---

## 1. 시작 전 체크리스트

### 1.1 필수 전제
- 로그인 가능한 계정이 준비되어 있음
- 현재 역할(Role)을 알고 있음: `owner` / `admin` / `member`
- 초기 구축 담당자는 `owner` 권한 사용을 권장

### 1.2 Scope 이해
metel은 화면과 데이터가 `scope` 기준으로 분리됩니다.
- `Organization`: 조직 전체 정책, 보안 기준선, 감사 설정
- `Team`: 팀 운영 정책, API Key, 사용량/감사 이벤트
- `User`: 개인 계정 보안, OAuth 연결, 본인 요청

중요 원칙
- Organization 정책은 baseline(최소 기준)입니다.
- Team 정책은 baseline보다 느슨하게 설정할 수 없습니다.
- User 설정은 본인 계정에만 적용됩니다.

---

## 2. Organization 설정 (초기 구축 핵심)

> 목표: 조직 운영에 필요한 기본 거버넌스와 보안 통제를 먼저 고정한다.

### Step O-1. Organization 생성
경로: `Organization > Organizations`

무엇을 하나요
- 신규 Organization을 생성하고 기본 운영 단위를 만든다.

입력 항목(예시)
- Organization Name: `Acme Corp` (실제 회사/법인 기준)

왜 필요한가
- 모든 Team, Member, 정책, 감사 로그가 Organization 단위로 귀속되기 때문

완료 기준
- Organization 목록에 신규 조직이 생성됨
- 조직 상세 조회가 가능함

실수 방지
- 테스트 조직과 운영 조직 이름을 명확히 분리(`-dev`, `-prod` 접미사 권장)

---

### Step O-2. 첫 관리자(Admin)와 운영 멤버 초대
경로: `Organization > Organizations` (Users/Invites/Requests 탭)

무엇을 하나요
- 운영에 필요한 사용자들을 초대하고 역할을 부여한다.

입력 항목(예시)
- Email: `admin@company.com`, `ops@company.com`
- Role: `admin` 또는 `member`
- Invite Expiration(있다면): 7~14일 권장

왜 필요한가
- Owner 1인 체제는 운영 리스크가 높음(휴가/퇴사/장애 대응)
- 운영/감사 업무 분리를 위해 최소 2명 이상의 admin 권장

완료 기준
- 초대 상태가 `pending` 또는 `accepted`로 확인됨
- 최소 1명 이상의 admin이 onboarding 완료

실수 방지
- 일반 사용자에게 admin을 과도하게 부여하지 않기
- 역할 변경 시 사유를 남겨 감사 추적성 확보

---

### Step O-3. 역할/권한 운영 원칙 확정
경로: `Organization > Organizations` (Role 관리)

무엇을 하나요
- 역할별 책임 범위를 문서화하고 실제 역할에 반영한다.

권장 권한 모델
- owner: 조직 정책 최종 승인, 고위험 변경
- admin: 초대/승인/정책 운영, 감사 설정 관리
- member: 조회 및 제한된 작업 수행

왜 필요한가
- UI 접근 가능 여부와 실제 API 실행 권한 불일치 리스크를 줄이기 위해

완료 기준
- 역할 매트릭스가 팀에 공유됨
- 실제 사용자 역할이 매트릭스와 일치

---

### Step O-4. OAuth Governance 설정
경로: `Organization > OAuth Governance`

무엇을 하나요
- 조직 차원에서 허용 Provider와 필수 Provider를 정의한다.

입력 항목(화면 기준)
- Allowed Providers: 사용 허용할 Provider 목록
- Required Providers: 필수 연결 Provider 목록
- (있다면) 정책 저장/배포 버튼

권장 초기값
- Allowed: 실제 업무에 필요한 Provider만 선택(Notion, Linear 등)
- Required: 반드시 필요한 항목만 최소화

왜 필요한가
- 구성원마다 임의 연결 시 보안/컴플라이언스 위험 증가
- 필수 연결 강제로 운영 표준화 가능

완료 기준
- 정책 저장 성공
- 정책 위반 사용자 상태를 확인 가능

실수 방지
- Required를 과도하게 설정하면 초기 사용자 이탈 증가
- 정책 변경 전 영향받는 팀/사용자 공지

---

### Step O-5. Audit Settings 설정
경로: `Organization > Audit Settings`

무엇을 하나요
- 감사 로그의 보존기간, 수집 수준 등 감사 정책을 정한다.

입력 항목(화면 기준)
- Retention Days/Window
- Audit Level 또는 Event Category(지원되는 경우)
- 기타 정책 JSON/옵션

권장 초기값
- 보존기간: 내부 규정이 없으면 최소 90일 이상
- 민감 작업(권한 변경, 키 회전, 정책 수정) 이벤트는 항상 기록

왜 필요한가
- 사고 대응, 원인 분석, 내부통제 증적 확보에 필수

완료 기준
- 정책 저장 후 반영된 설정 조회 가능

실수 방지
- 보존기간을 너무 짧게 잡으면 사후 추적 불가

---

### Step O-6. Admin/Ops 운영 절차 정리
경로: `Organization > Admin / Ops`

무엇을 하나요
- 운영용 액션(점검/복구/관리)을 실행하기 전 표준 절차를 정한다.

필수 운영 원칙
- 실행 전: 목적, 영향 범위, 롤백 가능 여부 확인
- 실행 후: 결과 로그와 수행자 기록 남기기

왜 필요한가
- 고위험 운영 액션의 오남용 방지

완료 기준
- Admin/Ops 실행 체크리스트를 팀에 공유

---

## 3. Team 설정 (서비스 운영 단위)

> 목표: 팀별 정책과 API 사용 통제를 구성하고 운영 모니터링 체계를 만든다.

### Step T-1. Team 생성 및 멤버 배치
경로: `Team > Team Policy` (팀 생성/멤버 관리 영역)

무엇을 하나요
- Organization 내부에 Team을 만들고 멤버를 배치한다.

입력 항목(예시)
- Team Name: `product-ai`, `ops-automation`
- Description(있다면): 팀 목적과 담당 업무
- Member Role: 팀 관리자는 최소 1명 지정

왜 필요한가
- 정책/API Key/감사 이벤트를 팀 단위로 분리해 운영하기 위해

완료 기준
- Team 목록에서 신규 팀 확인
- 팀별 멤버가 정상 배정

---

### Step T-2. Team Policy 작성
경로: `Team > Team Policy`

무엇을 하나요
- 팀에서 허용할 도구/행위 범위를 정책으로 정의한다.

입력 항목(화면 기준)
- Policy Name/Version
- Policy JSON 또는 Rule 입력 필드
- Effective Scope(팀 적용 범위)

작성 가이드
- 최소권한 원칙: 필요한 도구만 허용
- 고위험 액션(삭제, 대량 변경)은 명시적으로 제한
- Organization baseline 위반 없이 동일/강화 방향으로 작성

왜 필요한가
- 팀별 운영 특성에 맞춘 보안 통제 가능

완료 기준
- 정책 저장 성공
- 정책 Revision 이력에 기록됨

실수 방지
- JSON 문법 오류 방지: 저장 전 검증
- 단번에 큰 정책 변경 대신 소규모 변경 후 검증

---

### Step T-3. Policy Simulator 사전 검증
경로: `Team > Policy Simulator`

무엇을 하나요
- 실제 배포 전에 허용/차단 결과를 시뮬레이션한다.

입력 항목(화면 기준)
- API Key 선택
- Tool Name
- Arguments(JSON)

왜 필요한가
- 배포 후 차단 사고/업무 중단을 사전에 줄이기 위해

완료 기준
- 핵심 시나리오에 대해 Allow/Deny 결과가 기대와 일치

실수 방지
- 실제 운영에 쓰는 대표 시나리오를 반드시 테스트

---

### Step T-4. Team API Key 생성/회전 정책 적용
경로: `Team > API Keys`

무엇을 하나요
- 팀에서 사용하는 API Key를 생성하고 수명주기(회전/폐기)를 관리한다.

입력 항목(화면 기준)
- Name: `team-purpose-env` 형식 권장 (`ops-bot-prod`)
- Allowed Tools: 필요한 도구만 선택
- Expires At(있다면): 단기 만료 우선
- Description/Metadata: 사용처 명시

왜 필요한가
- 키 유출 및 과권한 사용 리스크를 줄이기 위해

완료 기준
- 키 생성 후 1회 테스트 호출 성공
- 키 보관 위치(Secret Manager 등) 확정
- 회전 일정(예: 30/60/90일) 수립

실수 방지
- 키를 채팅/문서에 평문 공유 금지
- 퇴사/권한 변경 시 즉시 폐기

---

### Step T-5. Usage 모니터링 기준선 설정
경로: `Team > Usage`

무엇을 하나요
- 호출량, 실패율, 지연시간 등 운영 지표를 기준선으로 정의한다.

입력/조작 항목
- 기간 필터(`24h`, `7d`)
- 도구/상태 필터(있다면)

왜 필요한가
- 이상 징후(급증, 실패율 상승)를 조기 감지하기 위해

완료 기준
- 팀별 정상 범위(평시 호출량, 허용 실패율)를 문서화

---

### Step T-6. Audit Events 운영 루틴화
경로: `Team > Audit Events`

무엇을 하나요
- 누가, 언제, 어떤 액션을 수행했는지 팀 단위로 추적한다.

입력/조작 항목
- User / Tool / Action 필터
- 기간 필터
- Event detail 조회

왜 필요한가
- 정책 위반, 오남용, 장애 원인 분석 속도 향상

완료 기준
- 주기적 점검 루틴(일/주 단위) 확정

---

### Step T-7. Agent Guide 활용
경로: `Team > Agent Guide`

무엇을 하나요
- `list_tools`, `call_tool` JSON-RPC 예시를 복사해 통합 테스트를 수행한다.

왜 필요한가
- API Key/정책/OAuth가 실제 호출에 문제없는지 빠르게 검증 가능

완료 기준
- 핵심 도구 1개 이상 `call_tool` 성공

---

## 4. User 설정 (개인 계정 준비)

> 목표: 각 사용자가 안전하고 일관된 상태로 서비스를 사용하도록 한다.

### Step U-1. Profile 설정
경로: `User > Profile`

무엇을 하나요
- 사용자 표시명/기본 정보를 점검한다.

입력 항목
- 표시명, 프로필 관련 필드

왜 필요한가
- 감사 로그와 협업 시 식별 정확도 향상

완료 기준
- 팀이 사용자 식별 가능

---

### Step U-2. Security 강화
경로: `User > Security`

무엇을 하나요
- 계정 보안 설정을 강화한다.

입력 항목
- 비밀번호 변경
- 2FA/MFA(지원 시)
- 세션 점검

왜 필요한가
- 계정 탈취 시 조직 전체 리스크로 확산될 수 있음

완료 기준
- 보안 정책 준수 상태 확인

---

### Step U-3. OAuth Connections 연결
경로: `User > OAuth Connections`

무엇을 하나요
- 본인 업무에 필요한 Provider를 연결한다.

입력/조작 항목
- Provider별 Connect/Disconnect
- 연결 상태 확인

왜 필요한가
- 도구 호출 시 사용자 OAuth 기반 권한이 필요할 수 있음

완료 기준
- 필수 Provider 연결 완료
- 불필요 연결 해제 완료

---

### Step U-4. My Requests 사용
경로: `User > My Requests`

무엇을 하나요
- 본인 요청 이력과 승인 상태를 확인한다.

왜 필요한가
- 권한 요청/변경 요청 처리 상태를 추적 가능

완료 기준
- 미처리 요청과 완료 요청을 구분해 관리

---

## 5. 역할별 권장 온보딩 플로우

### 5.1 Owner
1. Organization 생성
2. Admin 1~2명 지정
3. OAuth Governance/Audit Settings 설정
4. Team 구조 확정
5. Team Policy/API Key 운영 승인

### 5.2 Admin
1. Member 초대 및 역할 정리
2. Team 생성/멤버 배치
3. Team Policy + Simulator 검증
4. Usage/Audit 운영 루틴 수립

### 5.3 Member
1. Profile/Security/OAuth 개인 설정
2. Team 정책 범위 내 업무 수행
3. 필요 시 My Requests로 권한 요청

---

## 6. 메뉴별 상세 가이드 (현재 화면 기준)

> 아래 항목은 “무엇을 설정하는 메뉴인지”, “어떤 값을 넣는지”, “왜 필요한지”를 기준으로 정리했습니다.

### 6.1 Organization > Organizations
- 무엇: 조직/멤버/초대/요청 관리
- 어떤 값을 넣나
  - 조직명: 실제 조직 식별 가능한 명칭
  - 초대 이메일: 회사 도메인 사용 권장
  - 역할: owner/admin/member 중 최소권한
- 왜: 조직 단위 거버넌스와 책임 경계 설정

### 6.2 Organization > Integrations (Webhooks)
- 무엇: 조직 이벤트 외부 연동
- 어떤 값을 넣나
  - Endpoint URL: 수신 서버 HTTPS URL
  - Event Type: 필요한 이벤트만 선택
  - Secret: 랜덤 고강도 문자열
- 왜: 외부 시스템과 자동화 연동

### 6.3 Organization > OAuth Governance
- 무엇: OAuth 공급자 허용/필수 정책
- 어떤 값을 넣나
  - Allowed Providers: 허용 목록
  - Required Providers: 필수 목록
- 왜: 조직 보안 표준 및 연결 일관성 유지

### 6.4 Organization > Audit Settings
- 무엇: 감사 수집/보존 정책
- 어떤 값을 넣나
  - Retention Days: 규정 기반(예: 90/180/365)
  - 감사 레벨: 민감 이벤트 포함
- 왜: 사고 대응/컴플라이언스 증빙

### 6.5 Organization > Admin / Ops
- 무엇: 운영자 전용 점검/운영 액션
- 어떤 값을 넣나
  - 실행 대상/파라미터/사유
- 왜: 장애 대응 및 운영 유지보수

### 6.6 Team > Overview
- 무엇: 팀 핵심 지표 대시보드
- 어떤 값을 넣나
  - 기간 필터(24h/7d)
- 왜: 팀 상태를 빠르게 파악

### 6.7 Team > Usage
- 무엇: 도구 호출량/실패율/트렌드
- 어떤 값을 넣나
  - 기간, 도구, 상태 필터
- 왜: 비용/품질/안정성 모니터링

### 6.8 Team > Team Policy
- 무엇: 팀 정책 규칙 및 멤버십 관리
- 어떤 값을 넣나
  - Policy JSON/Rule
  - 팀 생성/멤버 역할
- 왜: 팀별 최소권한/운영 통제

### 6.9 Team > Agent Guide
- 무엇: JSON-RPC 호출 예시
- 어떤 값을 넣나
  - API Key, tool_name, arguments
- 왜: 연동 테스트 시작점 제공

### 6.10 Team > API Keys
- 무엇: 팀 API Key 수명주기 관리
- 어떤 값을 넣나
  - Name, Allowed Tools, Expires At
- 왜: 인증/권한 통제 및 키 유출 대응

### 6.11 Team > Policy Simulator
- 무엇: 정책 사전 검증
- 어떤 값을 넣나
  - API Key, Tool Name, Arguments
- 왜: 배포 전 차단 사고 예방

### 6.12 Team > Audit Events
- 무엇: 팀 단위 감사 이벤트 조회
- 어떤 값을 넣나
  - 사용자/도구/기간 필터
- 왜: 문제 원인 추적 및 내부통제

### 6.13 User > My Requests
- 무엇: 개인 요청 이력 확인
- 어떤 값을 넣나
  - 상태/기간 필터
- 왜: 승인/처리 진행상태 추적

### 6.14 User > Security
- 무엇: 개인 보안 설정
- 어떤 값을 넣나
  - 비밀번호/인증/세션 관련 값
- 왜: 계정 보안 강화

### 6.15 User > OAuth Connections
- 무엇: 개인 OAuth 연결 관리
- 어떤 값을 넣나
  - Provider 연결/해제
- 왜: 사용자 컨텍스트 도구 사용 보장

---

## 7. 권장 운영 기준(초기 2주)
- Day 1-2: Organization/OAuth/Audit baseline 완료
- Day 3-5: Team 정책 및 API Key 배포
- Day 6-10: Usage/Audit 모니터링으로 튜닝
- Day 11-14: 역할/권한/정책 리뷰 및 문서 업데이트

---

## 8. 자주 발생하는 문제와 해결

### 문제 1. 특정 메뉴가 보이지 않음
- 원인: 역할 부족 또는 scope 불일치
- 해결: 역할 확인 후 `scope`(org/team/user) 재선택

### 문제 2. 정책 저장은 되는데 호출이 차단됨
- 원인: Organization baseline 또는 OAuth 정책 위반
- 해결: Team Policy와 Organization 정책 동시 점검

### 문제 3. API Key는 있는데 실행 실패
- 원인: Allowed Tools 미설정, 만료, OAuth 미연결
- 해결: 키 스코프/만료/연결 상태 재확인

### 문제 4. 감사 로그가 충분하지 않음
- 원인: Audit Settings 보존기간/수집수준 과소 설정
- 해결: Organization Audit Settings 상향

---

## 9. 문서 유지관리 원칙
- UI 필드/메뉴 구조 변경 시 즉시 문서 업데이트
- 정책 JSON 예시는 운영 반영 전 시뮬레이터로 검증
- 분기별 1회 이상 역할/권한 모델 리뷰
