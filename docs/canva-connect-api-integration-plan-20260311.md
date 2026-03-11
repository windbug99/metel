# Canva Connect API 연동 정리 및 구현 계획

작성일: 2026-03-11

## 1. 요약

Canva Connect API는 단순 OAuth 연동이 아니라, 사용자 대신 Canva 리소스를 읽고 쓰는 REST API 묶음이다. 공식 문서 기준으로 현재 확인되는 주요 영역은 다음과 같다.

- Authentication
- Assets
- Autofill
- Brand templates
- Comments
- Designs
- Design imports
- Exports
- Folders
- Resizes
- Users
- Webhooks / Webhook notifications
- Keys API

현재 이 저장소는 `backend/app/routes/{provider}.py` 단위로 OAuth provider를 붙이고, `oauth_tokens` 테이블에 토큰을 저장하며, 프론트는 `/dashboard/integrations/oauth`에서 provider 상태를 렌더링하는 구조다. Canva도 이 패턴을 재사용할 수 있지만, 기존 provider들과 달리 **OAuth 2.0 Authorization Code + PKCE** 와 **refresh token 회전**을 반드시 고려해야 한다.

## 2. 공식 문서 기준 연결 가능한 API

### 2.1 Authentication

Canva Connect는 OAuth 2.0 Authorization Code with PKCE(SHA-256)를 사용한다.

- 사용자 인가 URL: `https://www.canva.com/api/oauth/authorize`
- 토큰 발급 URL: `POST https://api.canva.com/rest/v1/oauth/token`
- 토큰 introspect / revoke 지원
- 액세스 토큰은 짧게 유지되고 refresh token으로 재발급하는 구조
- refresh token은 1회 사용성으로 관리해야 한다

이 저장소 영향:

- 현재 Google/GitHub/Linear/Notion 라우트는 state 기반 OAuth는 이미 있으나 PKCE 저장 구조는 없음
- `oauth_tokens` 테이블은 `refresh_token`, `expires_at`, `provider_account_id`, `provider_metadata` 같은 필드가 없어 Canva에는 확장이 필요함

### 2.2 Users

연결 직후 사용자/팀 식별과 capability 점검에 바로 쓸 수 있다.

- `GET /rest/v1/users/me`
  - scope 없음
  - 사용자 `user_id`, `team_id` 확인 가능
- `GET /rest/v1/users/me/profile`
  - `profile:read`
  - 표시 이름 확인 가능
- `GET /rest/v1/users/me/capabilities`
  - `profile:read`
  - `autofill`, `brand_template`, `resize`, `team_restricted_app` capability 확인 가능

권장 용도:

- OAuth callback 직후 Canva 계정 식별
- capability 기반 기능 노출 제어
- 프론트에서 “이 사용자는 resize/autofill 가능 여부” 표시

### 2.3 Designs

기본 설계 조회/생성이 가능한 핵심 API다.

- `GET /rest/v1/designs`
  - `design:meta:read`
  - 디자인 목록, 검색, 정렬, continuation pagination
- `GET /rest/v1/designs/{designId}`
  - `design:meta:read`
  - 단건 메타데이터, edit/view URL, 썸네일
- `POST /rest/v1/designs`
  - `design:content:write`
  - 새 디자인 생성
- `GET /rest/v1/designs/{designId}/pages`
  - preview API
  - 디자인 페이지 메타데이터/페이지 썸네일

권장 용도:

- “Canva 디자인 선택기”
- 디자인 생성 후 edit URL로 Canva 에디터 이동
- 기존 metel 워크플로우에서 결과물을 Canva 디자인으로 열기

### 2.4 Exports

Canva 디자인을 외부 시스템으로 다시 가져오는 데 필요하다.

- `POST /rest/v1/exports`
  - 비동기 export job 생성
  - PDF, JPG, PNG, GIF, PPTX, MP4 지원
- `GET /rest/v1/exports/{exportId}`
  - job 상태와 다운로드 URL 조회
  - 다운로드 URL은 24시간 유효

권장 용도:

- 사용자가 Canva에서 수정한 결과를 metel 또는 외부 스토리지로 회수
- Slack/메일/문서 파이프라인에 export 결과 연결

### 2.5 Assets

이미지/영상 업로드 및 메타데이터 관리가 가능하다.

- `POST /rest/v1/asset-uploads`
  - `asset:write`
  - binary 업로드 job
- `GET /rest/v1/asset-uploads/{jobId}`
  - `asset:read`
  - 업로드 job 결과 조회
- `POST /rest/v1/url-asset-uploads`
  - preview API
  - URL 기반 업로드 job
- `GET /rest/v1/assets/{assetId}`
  - `asset:read`
- `PATCH /rest/v1/assets/{assetId}`
  - `asset:write`
  - 이름/태그 수정
- `DELETE /rest/v1/assets/{assetId}`
  - `asset:write`
  - 휴지통 이동

권장 용도:

- metel에서 생성한 이미지/리소스를 Canva 프로젝트로 푸시
- 사용자가 업로드한 자산 태깅/정리 자동화

### 2.6 Folders

프로젝트 정리용 폴더 계층을 다룬다.

- `POST /rest/v1/folders`
  - `folder:write`
- `GET /rest/v1/folders/{folderId}`
- `PATCH /rest/v1/folders/{folderId}`
- `DELETE /rest/v1/folders/{folderId}`
- `GET /rest/v1/folders/{folderId}/items`
  - `folder:read`
  - design / folder / image 조회
- `POST /rest/v1/folders/move`
  - `folder:write`

권장 용도:

- 조직/팀별 Canva 산출물 정리
- metel 작업 단위와 Canva 폴더 구조 매핑

### 2.7 Brand templates

Enterprise 중심 기능이다.

- `GET /rest/v1/brand-templates`
  - `brandtemplate:meta:read`
- `GET /rest/v1/brand-templates/{brandTemplateId}`
- `GET /rest/v1/brand-templates/{brandTemplateId}/dataset`
  - `brandtemplate:content:read`
  - autofill 가능한 필드 정의 조회

제약:

- Canva Enterprise 조직 사용자여야 함
- 2025년 9월 brand template ID 형식 변경 이력이 있어 ID 저장 시 주의 필요

권장 용도:

- 기업용 템플릿 기반 자동 문서/배너/제안서 생성

### 2.8 Autofill

브랜드 템플릿에 데이터를 넣어 개인화된 디자인을 만드는 비동기 API다.

- `POST /rest/v1/autofills`
  - 브랜드 템플릿 + 입력 데이터로 디자인 생성 job
- `GET /rest/v1/autofills/{jobId}`
  - 결과 디자인 조회

제약:

- Canva Enterprise 사용자 필요
- `users/me/capabilities` 로 `autofill` capability 사전 확인 권장
- 이미지/text/chart 타입 필드 입력 지원

권장 용도:

- 개인화 배너, 초대장, 리포트, 제안서 자동 생성
- metel의 structured input -> Canva 브랜드 템플릿 결과물

### 2.9 Design imports

외부 파일을 Canva 디자인으로 가져오는 기능이다.

- `POST /rest/v1/imports`
  - `design:content:write`
  - binary 파일 import job
- `GET /rest/v1/imports/{jobId}`
- `POST /rest/v1/url-imports`
  - URL import job
- `GET /rest/v1/url-imports/{jobId}`

권장 용도:

- metel에서 만든 PPT/PSD/PDF/기타 문서를 Canva 편집 가능한 디자인으로 변환
- 외부 생성물을 Canva 협업 흐름에 편입

### 2.10 Resizes

디자인 복제 + 새 크기 변환 기능이다.

- `POST /rest/v1/resizes`
  - `design:content:read`
  - `design:content:write`
  - capability `resize` 필요
- `GET /rest/v1/resizes/{jobId}`

제약:

- Pro 등 premium 기능 사용자 대상
- in-place resize는 아니고 새 디자인 생성
- capability 없으면 403 가능
- 일부 무료 사용자는 quota trial이 있을 수 있음

권장 용도:

- 한 원본 디자인을 채널별 규격으로 파생 생성

### 2.11 Comments

디자인 협업 코멘트 API다. 현재 preview 비중이 높다.

- `POST /rest/v1/designs/{designId}/comments`
  - preview
  - `comment:write`
  - thread 생성
- `GET /rest/v1/designs/{designId}/comments/{threadId}`
  - preview
  - `comment:read`
- `POST /rest/v1/designs/{designId}/comments/{threadId}/replies`
  - preview
  - `comment:write`
- `GET /rest/v1/designs/{designId}/comments/{threadId}/replies`
  - preview
  - `comment:read`
- `GET /rest/v1/designs/{designId}/comments/{threadId}/replies/{replyId}`
  - preview
  - `comment:read`

권장 용도:

- 리뷰 코멘트를 외부 승인 흐름과 연결
- 다만 preview이므로 1차 출시 범위에서는 제외하는 편이 안전

### 2.12 Webhooks / Keys API

Canva에서 사용자 관련 이벤트를 실시간으로 받을 수 있다.

- Webhook notifications
  - comment
  - suggestion
  - share design
  - share folder
  - design approval
  - design access request
  - folder access request
  - team invite
- `GET /rest/v1/connect/keys`
  - preview
  - 서명 검증용 JWKS 조회
  - key rotation 캐시 권장

제약:

- webhook 기능 자체가 preview
- 공개 배포 integration에는 preview 사용 불가
- 이벤트별 요구 scope 조합이 다름

권장 용도:

- Canva 코멘트/공유 이벤트를 metel 알림 파이프라인에 연결
- 다만 1차 구현에는 polling 기반 상태 조회가 더 안정적

## 3. 스코프 설계

공식 scope 목록 중 metel 1차 구현에 의미 있는 것만 추리면 다음과 같다.

### 최소 읽기 중심

- `design:meta:read`
- `profile:read`

### 디자인 생성/내보내기 포함

- `design:meta:read`
- `design:content:write`
- `profile:read`

### 자산 업로드 포함

- `asset:read`
- `asset:write`
- `folder:read`
- `folder:write`
- `design:meta:read`
- `design:content:write`
- `profile:read`

### Enterprise 템플릿 자동화 포함

- `brandtemplate:meta:read`
- `brandtemplate:content:read`
- `design:meta:read`
- `design:content:write`
- `profile:read`

중요:

- Canva는 scope 상속이 없다. 예를 들어 `asset:write` 만으로 `asset:read` 가 생기지 않는다.
- scope는 Developer Portal 설정값과 OAuth 요청값 둘 다 일치해야 한다.

### 전체 구현 기능 사용용 권장값

현재 저장소에 구현된 Canva 기능 전체를 쓰려면 `CANVA_SCOPES` 를 아래처럼 맞추는 것이 기준값이다.

`profile:read design:meta:read design:content:read design:content:write asset:read asset:write comment:read comment:write brandtemplate:meta:read brandtemplate:content:read folder:read folder:write`

기능 매핑:

- 연결/프로필/디자인 조회: `profile:read design:meta:read`
- 디자인 생성/export/resize/import: `design:content:read design:content:write`
- asset metadata / URL upload: `asset:read asset:write`
- comments / replies: `comment:read comment:write`
- brand templates / dataset: `brandtemplate:meta:read brandtemplate:content:read`
- folders: `folder:read folder:write`

## 4. metel 기준 추천 구현 범위

### Phase 1. 반드시 구현

목표: 사용자 연결, 디자인 목록, 기본 생성, export까지

- OAuth + PKCE + token refresh
- Canva status/connect/disconnect UI
- `users/me`, `users/me/profile` 기반 계정 식별
- `designs list/get/create`
- `exports create/get`

이 단계만으로도 “metel -> Canva 디자인 생성 -> 사용자가 Canva 편집 -> 결과 export” 흐름이 성립한다.

### Phase 2. 실사용 가치가 큰 확장

- asset upload
- folder create/list/move
- return navigation
- design imports

이 단계부터 metel 산출물을 Canva 작업공간으로 넣고, 다시 외부로 가져오는 왕복 흐름이 완성된다.

### Phase 3. Enterprise / 고급 기능

- brand templates
- autofill
- resize
- webhook notifications

이 단계는 기능 임팩트는 크지만, plan/capability/preview 제약이 있으므로 Enterprise 고객 니즈가 확인된 뒤 여는 편이 맞다.

## 5. 저장소 기준 구현 계획

### 5.1 백엔드 설정 확장

대상 파일:

- `backend/app/core/config.py`
- `backend/.env.example`

추가 필요 env:

- `CANVA_CLIENT_ID`
- `CANVA_CLIENT_SECRET`
- `CANVA_REDIRECT_URI`
- `CANVA_STATE_SECRET`
- `CANVA_SCOPES`

추가 권장 env:

- `CANVA_API_BASE_URL=https://api.canva.com/rest/v1`
- `CANVA_OAUTH_AUTHORIZE_URL=https://www.canva.com/api/oauth/authorize`
- `CANVA_TOKEN_ENCRYPTION_KEY` 또는 기존 토큰 암호화 키 재사용 정책 명시

### 5.2 OAuth 저장소 스키마 확장

현재 `oauth_tokens` 는 Canva에 필요한 만료/갱신 정보를 충분히 담지 못한다.

대상 파일:

- `docs/sql/002_create_oauth_tokens_table.sql`
- 신규 migration 추가 필요

추가 권장 컬럼:

- `refresh_token_encrypted text`
- `token_expires_at timestamptz`
- `provider_account_id text`
- `provider_team_id text`
- `provider_metadata jsonb`

이유:

- Canva refresh token 회전 처리 필요
- `users/me` 결과의 `user_id`, `team_id` 저장 필요
- capability/plan/연결 메타데이터 저장 여지 확보

### 5.3 PKCE 저장 전략 추가

현재 provider 라우트는 `state` 만 관리한다. Canva는 `code_verifier` 가 필요하다.

구현 방향:

- `state` 생성 시 서버 저장소에 `code_verifier` 함께 저장
- callback 시 `state` 검증 후 `code_verifier` 로 토큰 교환
- 사용 후 즉시 폐기

권장 저장 위치:

- 1안: Supabase 임시 테이블 `oauth_pending_states`
- 2안: signed/encrypted state payload

권장 판단:

- 서버 검증/재시도/만료처리를 고려하면 임시 테이블 방식이 안전

### 5.4 Canva OAuth 라우트 추가

신규 파일:

- `backend/app/routes/canva.py`

엔드포인트 초안:

- `POST /api/oauth/canva/start`
- `GET /api/oauth/canva/callback`
- `GET /api/oauth/canva/status`
- `DELETE /api/oauth/canva/disconnect`

추가 내부 동작:

- authorization URL 생성 시 PKCE challenge 포함
- callback 에서 token exchange
- `users/me` 와 `users/me/profile` 호출
- `oauth_tokens` upsert
- refresh token 저장

### 5.5 토큰 재발급 공통화

현재 provider 라우트는 access token만 저장하는 구조가 많다. Canva는 refresh 흐름이 사실상 필수라서 공통 계층으로 분리하는 편이 낫다.

권장 추가 파일:

- `backend/app/integrations/oauth_store.py`
- `backend/app/integrations/canva_client.py`

핵심 함수:

- `load_provider_token(user_id, provider)`
- `refresh_canva_access_token_if_needed(...)`
- `call_canva_api(...)`
- `poll_canva_job(...)`

### 5.6 백엔드 라우트 등록

대상 파일:

- `backend/main.py`

작업:

- `canva_router` import
- `app.include_router(canva_router)` 추가

### 5.7 프론트 OAuth 화면 반영

대상 파일:

- `frontend/app/dashboard/(v2)/integrations/oauth/page.tsx`

현재 이 파일은 provider 목록이 고정이다.

필수 변경:

- `OAuthProvider` 타입에 `canva` 추가
- `providerLogoSrc()` 에 Canva 로고 추가
- status fetch 목록에 `/api/oauth/canva/status` 추가
- connect/disconnect UI 카드에 Canva 추가
- 조직 정책 provider catalog 초기 목록에 `canva` 추가
- Tooltip/설명 문구를 “Notion, Linear, GitHub, Canva” 로 확장

### 5.8 에이전트 도구 노출

이 프로젝트는 agent tool registry 구조가 이미 있다.

후속 대상:

- `backend/agent/tool_specs/`
- `backend/agent/skills/contracts/`

1차 도구 후보:

- `canva_design_list`
- `canva_design_create`
- `canva_export_create`
- `canva_export_get`

2차 도구 후보:

- `canva_asset_upload`
- `canva_folder_list_items`
- `canva_brand_template_list`
- `canva_autofill_create`

## 6. 권장 API 우선순위

이 저장소 기준으로는 아래 순서가 가장 효율적이다.

1. OAuth + `users/me`
2. `designs list/get`
3. `designs create`
4. `exports create/get`
5. `assets` + `folders`
6. `design imports`
7. `brand templates` + `autofill`
8. `resize`
9. `comments`
10. `webhooks`

이유:

- 1~4단계만으로도 사용자 가치가 분명함
- 5~7단계는 확장성은 높지만 데이터 모델과 UX 설계가 더 필요함
- 8~10단계는 capability/preview/플랜 의존성이 큼

## 7. 구현 시 주의사항

### 7.1 Preview API 분리

공식 문서상 아래는 preview 또는 preview 비중이 높다.

- comments
- webhook notifications
- keys API
- designs pages
- URL asset uploads

정책:

- 1차 운영 배포 범위에서 제외
- feature flag 뒤에 숨김
- public integration 목표라면 preview 사용 금지

### 7.2 Capability 체크 선행

다음은 capability가 중요하다.

- `resize`
- `autofill`
- `brand_template`

실행 전에 `GET /users/me/capabilities` 로 선확인해야 한다.

### 7.3 비동기 job poll 표준화

다음 영역은 모두 job 기반이다.

- exports
- asset uploads
- design imports
- autofill
- resize

공식 문서는 exponential backoff polling을 권장한다. 따라서 provider별 임시 구현보다 공통 poller를 두는 편이 맞다.

### 7.4 return navigation 활용

Canva 편집으로 이동시키는 기능을 붙일 경우, 단순 `edit_url` 링크만 여는 것보다 return navigation을 같이 설계해야 사용자 경험이 좋아진다.

추천 흐름:

- metel에서 디자인 생성/조회
- Canva `edit_url` 로 이동
- Canva 편집 후 metel로 복귀
- 복귀 시 디자인 상태/썸네일/최종 export 갱신

## 8. 제안 일정

### Sprint 1

- OAuth + PKCE 저장소
- DB migration
- Canva provider backend route
- OAuth dashboard UI 연결

### Sprint 2

- designs list/get/create
- users/me/profile/capabilities
- basic export workflow
- 기본 에러/재인증 UX

### Sprint 3

- assets/folders
- return navigation
- design imports

### Sprint 4

- brand templates/autofill
- resize
- 필요 시 webhook PoC

## 9. 최종 권장안

이 저장소에 Canva를 붙일 때 가장 현실적인 1차 목표는 아래다.

- Canva OAuth 연결
- 사용자 Canva 계정/팀 식별
- 디자인 목록 조회
- 새 디자인 생성
- Canva 편집 링크 이동
- 편집 결과 export

이 범위는 preview 의존성이 낮고, 현재 metel 구조에 가장 자연스럽게 맞는다. 그 다음 단계로 asset/folder/import를 추가하면 “외부 시스템 <-> Canva” 왕복 연동이 완성되고, Enterprise 고객이 실제로 필요할 때 brand template/autofill/resize를 여는 구성이 적절하다.

## 10. 참고 문서

- Overview: https://www.canva.dev/docs/connect/
- Authentication: https://www.canva.dev/docs/connect/authentication/
- API requests and responses: https://www.canva.dev/docs/connect/api-requests-responses/
- Scopes: https://www.canva.dev/docs/connect/appendix/scopes/
- Capabilities: https://www.canva.dev/docs/connect/capabilities/
- Return navigation guide: https://www.canva.dev/docs/connect/return-navigation-guide/
- Designs overview: https://www.canva.dev/docs/connect/api-reference/designs/
- Exports create: https://www.canva.dev/docs/connect/api-reference/exports/create-design-export-job/
- Assets overview: https://www.canva.dev/docs/connect/api-reference/assets/
- Folders overview: https://www.canva.dev/docs/connect/api-reference/folders/
- Design imports overview: https://www.canva.dev/docs/connect/api-reference/design-imports/
- Brand templates overview: https://www.canva.dev/docs/connect/api-reference/brand-templates/
- Autofill overview: https://www.canva.dev/docs/connect/api-reference/autofills/
- Users overview: https://www.canva.dev/docs/connect/api-reference/users/
- Webhooks overview: https://www.canva.dev/docs/connect/webhooks/
- Webhook keys: https://www.canva.dev/docs/connect/api-reference/webhooks/keys/

## 11. Claude Connector 기능 목록 기준 격차 분석

아래는 사용자가 제시한 Claude connector의 Canva 기능 목록을 기준으로, 2026-03-11 시점의 Canva Connect 공식 문서와 현재 metel 구현 상태를 대조한 결과다.

### 11.1 현재 metel에서 이미 있는 것

- `Search Designs`
  - 공식 대응: `GET /designs`
  - 현재 상태: 구현됨 (`canva_design_list`)
- `Get Design Information`
  - 공식 대응: `GET /designs/{designId}`
  - 현재 상태: 구현됨 (`canva_design_get`)
- `Export Design`
  - 공식 대응: `POST /exports` + `GET /exports/{exportId}`
  - 현재 상태: 구현됨 (`canva_export_create`, `canva_export_get`)
- `Get Export Formats`
  - 공식 대응: `GET /designs/{designId}/export-formats`
  - 현재 상태: backend route만 있음, agent tool 미노출
- `Resize Design`
  - 공식 대응: `POST /resizes` + `GET /resizes/{jobId}`
  - 현재 상태: 미구현
- `List Folder Items`
  - 공식 대응: `GET /folders/{folderId}/items`
  - 현재 상태: 미구현
- `Search Folders`
  - 공식 대응: 폴더 목록/검색 API 조합 필요
  - 현재 상태: 미구현
- `Create Folder`
  - 공식 대응: `POST /folders`
  - 현재 상태: 미구현
- `Move Item To Folder`
  - 공식 대응: `POST /folders/move`
  - 현재 상태: 미구현
- `Upload Asset From URL`
  - 공식 대응: `POST /url-asset-uploads` (preview)
  - 현재 상태: 미구현
- `Import Design From Public HTTPS URL`
  - 공식 대응: `POST /url-imports`
  - 현재 상태: 미구현
- `Add Comment To Design`
  - 공식 대응: comment thread 생성 API (preview)
  - 현재 상태: 미구현
- `Reply To Comment`
  - 공식 대응: comment reply 생성 API (preview)
  - 현재 상태: 미구현
- `List Comment Replies`
  - 공식 대응: comment replies 조회 API (preview)
  - 현재 상태: 미구현

### 11.2 공식 Connect 문서에서 확인되지만 metel에 아직 없는 것

- `Get Design Pages`
  - 공식 대응: pages preview API
- `List Design Comments`
  - 공식 대응: comments preview API 계열
- `List Brand Kits`
  - 공식 대응: 엄밀히는 `Brand kits`가 아니라 `Brand templates` API가 공식 문서에 있음
- `Get Design Page Thumbnail`
  - 공식 대응: pages/thumbnail 계열 preview API
- `Get Assets Metadata`
  - 공식 대응: `GET /assets/{assetId}` 또는 asset 목록 API 조합

### 11.3 공식 Connect 문서에서 직접 확인하지 못한 항목

아래 항목들은 공식 Connect API reference에서 직접 대응 엔드포인트를 확인하지 못했다. 이 판단은 공식 문서 검색 기준의 결론이며, private/beta 또는 Claude 전용 추상화일 가능성은 있다.

- `Generate Design with AI`
- `Generate Structured Design with AI`
- `Request User Review of Presentation Outline`
- `Resolve Shortlink`
- `Get Design Text Content`
- `Get Presenter Notes`
- `Create Design From Candidate`
- `Start Editing Design`
- `Edit Design`
- `Save Design Edits`
- `Discard Design Edits`
- `Merge Designs`

중요:

- 위 항목들은 현재 공개 Canva Connect만으로는 1:1 재현이 어려울 가능성이 높다.
- 따라서 “Claude connector와 동일 기능” 목표는 실제로는 두 층으로 나눠야 한다.
  - 공개 Connect API로 구현 가능한 층
  - 공식 공개 API 바깥의 AI/편집 세션형 기능 층

## 12. metel 작업 계획: Claude connector parity 기준

### Phase A. 공개 Connect API 기준 동등화

목표:

- Claude connector 목록 중 공식 Connect로 재현 가능한 항목을 우선 동일 수준으로 제공

범위:

- `Search Designs`
- `Get Design Information`
- `Get Export Formats`
- `Export Design`
- `List Folder Items`
- `Search Folders`
- `Get Assets Metadata`
- `Upload Asset From URL` (preview flag 뒤)
- `Import Design From Public HTTPS URL`
- `Create Folder`
- `Move Item To Folder`
- `List Design Comments` (preview flag 뒤)
- `List Comment Replies` (preview flag 뒤)
- `Add Comment To Design` (preview flag 뒤)
- `Reply To Comment` (preview flag 뒤)
- `Resize Design`
- `List Brand Kits`
  - metel 표기는 `Brand Kits` 로 유지하되, 실제 Canva API는 `Brand templates` 중심으로 연결

구현 작업:

1. backend Canva route 확장
   - `folders`
   - `assets`
   - `imports`
   - `resizes`
   - `comments`
   - `brand templates`
2. `backend/agent/tool_specs/canva.json` 확장
   - 위 API를 tool spec으로 등록
3. `backend/agent/tool_runner.py` 확장
   - async job형 API의 poll/result 표준화
4. `backend/agent/slot_schema.py` 확장
   - folder/design/asset/comment 식별자 해석 추가
5. `backend/app/core/resolver.py` 확장
   - `folder_name -> folder_id`
   - `asset_name/url -> asset_id`
   - `brand_template_name -> brand_template_id`
6. connector job history 반영
   - `imports`, `resizes`, `asset uploads`, `exports` 를 공통 job history에 저장

### Phase B. 사용자 경험 정리

목표:

- metel은 control plane에 집중하고, 세부 작업은 AI/agent에서 호출 가능하게 정리

범위:

- OAuth 화면은 연결/해제만 유지
- Policy simulator / MCP guide / agent tool docs에 Canva 도구 예시 추가
- connector history에서 Canva async job 추적 제공

구현 작업:

1. Policy simulator에 Canva tool set 표시
2. MCP guide에 Canva 예제를 Claude connector 수준으로 확장
3. agent prompt/template에 Canva examples 추가
4. 오류 메시지 표준화
   - capability 부족
   - preview 미허용
   - enterprise 전용
   - scope 부족

### Phase C. 비공개/미확인 기능 대응 전략

목표:

- Claude connector 목록 중 공개 Connect 문서에 없는 항목은 무리하게 가짜 구현하지 않고, 제품 정책을 먼저 정함

대상:

- AI 생성형 디자인
- structured design generation
- presentation outline review
- editing session lifecycle
- shortlink/text/presenter notes/merge

권장 전략:

1. 항목별 공식 근거 재검증
   - Canva Apps SDK / MCP / private beta / Claude abstraction 여부 확인
2. 공개 API에 없으면 metel 표준 기능으로 대체
   - `Generate Design with AI` → metel LLM이 copy/brief 생성 후 `Create Design` 또는 `Autofill` 로 연결
   - `Request User Review of Presentation Outline` → metel approval workflow + comment API로 대체
   - `Get Presenter Notes` / `Get Design Text Content` → 공식 추출 API가 없으면 미지원으로 남김
3. 제품 정책 명시
   - “Claude parity”가 아니라 “public Canva Connect parity”를 기준으로 삼음

현재 반영 상태:

- MCP Guide에 public Connect parity 예제를 추가함
- unsupported 항목은 제품 문서에서 명시적으로 비노출 처리
- metel은 control plane으로서 공개 Canva Connect API 범위만 직접 노출

## 13. 우선순위 제안

실행 순서는 아래가 가장 현실적이다.

1. Phase A-1
   - `Get Export Formats`
   - `Create Folder`
   - `Move Item To Folder`
   - `List Folder Items`
   - `Search Folders`
2. Phase A-2
   - `Import Design From Public HTTPS URL`
   - `Resize Design`
   - `Get Assets Metadata`
   - `Upload Asset From URL`
3. Phase A-3
   - comment 계열 preview API
   - brand template 계열
4. Phase C
   - AI/outline/edit-session 계열은 공개 API 지원 여부를 다시 확인한 뒤 별도 트랙으로 분리

이유:

- 1단계는 공개 정식 API 비중이 높고 구현 난도가 낮다.
- 2단계는 async job/history 모델 재사용 가치가 크다.
- 3단계는 preview 및 plan 제약이 있다.
- 4단계는 현재 정보만으로는 1:1 구현 가능성을 보장할 수 없다.
