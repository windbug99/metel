# Homepage UI Redesign Plan (2026-02-24)

## 목적
- `frontend/app/page.tsx`를 `droidclaw.ai` 스타일의 라이트 테마 랜딩으로 개편한다.
- metel의 포지셔닝을 "단순 챗봇"이 아닌 **신뢰 가능한 운영 실행 엔진**으로 명확히 전달한다.
- 현재 제공 범위(개인 설치 미제공, 연동 서비스 제한)를 정확하게 반영한다.

## 고정 요구사항
- 버튼: `Sign in`, `GitHub`만 노출
- 폰트: `Geist` 사용
- 테마: Light theme
- `Use case` 섹션: 실제 예시 요청문 기반 콘텐츠
- `현재 연동 가능 서비스 목록` 섹션 포함
- `Setup` 섹션 제거 (개인 설치 버전 미제공)
- 핵심 강조 항목:
  - LLM 보안 이슈
  - 다양한 서비스 조합
  - 동적 워크플로우 생성

## 메시지 전략 (핵심 카피 방향)
- metel 정의:
  - "LLM이 실제 업무 시스템을 안전하게 실행하는 운영 레이어"
- Slack/일반 자동화 툴 대비 차별점:
  - 다단계 실행(Plan -> Execute -> Verify -> Replan)
  - Cross-service orchestration
  - 실행 로그/검증/가드레일
- 가치 전달 우선순위:
  1. 실행 신뢰성
  2. 서비스 조합 실행력
  3. 운영 투명성(로그/검증)

## 페이지 섹션 구조 (안)
1. Hero
2. Why metel (핵심 차별점 3개)
3. Use Cases (예시 요청문)
4. Connected Services (현재 연동 가능 서비스)
5. Security & Reliability (LLM 보안 + 가드레일)
6. Final CTA (Sign in / GitHub)

## 섹션별 초안 문구

### 1) Hero
- Title:
  - "From Prompt to Operations."
- Subtitle:
  - "metel turns one sentence into verified multi-service execution across your actual work stack."
- 보조 문구:
  - "Not a chat UI layer. An execution engine with guardrails."

### 2) Why metel
- 카드 A: Dynamic Workflow Generation
  - "Generate execution graphs from a single request, then run with deterministic orchestration."
- 카드 B: Cross-Service Orchestration
  - "Calendar, Notion, Linear, Telegram flows executed as one operation."
- 카드 C: Verification by Default
  - "Validation, retries, rollback policies, and execution traces for reliable outcomes."

### 3) Use Cases (예시 요청문)
- "구글캘린더에서 오늘 회의일정 조회해서 각 회의마다 노션에 회의록 초안 생성하고 각 회의를 리니어 이슈로 등록해줘"
- "리니어의 기획 관련 이슈를 찾아 3문장으로 요약해서 노션 페이지로 만들어줘"
- "노션 페이지 내용을 기준으로 리니어 이슈 설명을 업데이트해줘"

### 4) Connected Services (현재 연동 가능)
- Notion
- Linear
- Google Calendar
- Telegram
- (Spotify는 현재 운영 제한 상태로 명시: Disabled/Experimental)

### 5) Security & Reliability
- 소제목:
  - "LLM Security Is an Execution Problem."
- 항목:
  - "Tool allowlist and scoped OAuth access"
  - "Schema-validated payloads and slot validation"
  - "Budget limits, duplicate blocking, and fallback control"
  - "Atomic failure handling with compensation (rollback) for multi-step runs"

### 6) Final CTA
- Primary: Sign in
- Secondary: GitHub
- 보조 문구:
  - "Track every execution with structured logs."

## 디자인/구현 가이드
- Typography:
  - Geist Sans 중심, 계층 강한 타이포(히어로 대제목 대비 강화)
- Color:
  - Light base + neutral grayscale + 1개 강조색만 사용
- Layout:
  - 넓은 여백, 섹션 경계 명확화, 과도한 장식 배제
- Motion:
  - 초기 로드 시 약한 페이드/슬라이드만 적용
- 반응형:
  - 모바일 1열, 데스크탑 2~3열 카드 구조

## 구현 범위
- 수정:
  - `frontend/app/page.tsx`
  - 필요 시 `frontend/app/globals.css`
  - 필요 시 `frontend/app/layout.tsx` (Geist 적용 상태 확인/보정)
- 비수정:
  - Dashboard, Auth 로직, Backend API

## 진행 상태 (2026-02-24)
- [x] `frontend/app/page.tsx` 랜딩 구조 전면 개편
- [x] 실배포 전 미세 조정 1차 반영 (문구 톤/섹션 여백/모바일 타이포)
- [x] 실배포 전 미세 조정 2차 반영 (긴 한글 요청문 줄바꿈/모바일 헤드라인 보정)
- [x] `Sign in`, `GitHub` CTA 구성 반영
- [x] `Use Cases` 예시 요청문 섹션 반영
- [x] `Connected Services` 섹션 반영
- [x] `Security & Reliability` 섹션 반영
- [x] `Setup` 섹션 제거
- [x] `AuthPanel` 버튼 라벨 커스터마이징(`signInLabel`) 추가
- [x] 타입 체크 검증 (`pnpm exec tsc --noEmit`)
- [x] 빌드 검증 시도 (`pnpm exec next build`) - 실행 환경 외부 네트워크 제한으로 Google Font fetch 실패 확인
- [ ] 실제 배포 화면 기준 최종 QA (모바일/데스크탑 시각 검수)

## 검증 체크리스트
- [x] 홈페이지에 `Sign in`, `GitHub` 버튼만 노출
- [x] 라이트 테마 유지
- [x] Geist 폰트 적용 확인
- [x] Setup 섹션 미노출 확인
- [x] Use case 요청문 3개 이상 노출
- [x] 현재 연동 서비스 목록 반영 확인
- [x] 핵심 강조 3요소(보안/조합/동적 워크플로우) 명시
- [ ] 모바일/데스크탑 레이아웃 정상 동작 (실배포 시각 검수 대기)

## 리스크 및 대응
- 리스크: marketing 카피 과장
  - 대응: 현재 구현/검증된 기능만 문구에 사용
- 리스크: 스타일 참조 사이트와 지나친 유사성
  - 대응: 레이아웃 방향만 참고, 카피/구성/비주얼은 metel 고유화
- 리스크: 폰트 미적용
  - 대응: layout 레벨에서 Geist className 강제 확인

## 완료 기준 (Definition of Done)
- 사용자 요구사항 6개(버튼/폰트/테마/use case/서비스목록/setup 제거) 모두 충족
- 핵심 강조 항목 3개가 페이지에서 즉시 식별 가능
- 카피가 metel의 방향성(실행 신뢰성 중심)을 일관되게 전달
