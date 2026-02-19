# Linear API Guide (metel)

## 목적
- Linear 연동 작업(이슈 조회/검색/생성)을 안정적으로 수행하기 위한 운영 기준 문서다.
- 에이전트는 본 문서를 참고해 계획을 수립하되, 실제 실행 가능한 도구는 `backend/agent/tool_specs/linear.json`으로 제한한다.

## 인증
- OAuth 2.0 Authorization Code Flow
- Access token을 `oauth_tokens`에 암호화 저장

## 권한
- 최소 `read` scope 필요
- 이슈 생성에는 `write` scope 필요

## 핵심 엔드포인트
- `POST /graphql` (Linear GraphQL API)

## 핵심 도구
- `linear_get_viewer`
- `linear_list_issues`
- `linear_search_issues`
- `linear_create_issue`

## 제한 사항
- GraphQL 응답에서 `errors`가 반환되면 실행 실패로 처리
- rate limit 대응 필요

## 에러 처리
- 401/403: 권한 재승인
- 429: backoff 후 재시도
- GraphQL errors: 입력/권한/스키마 확인

## 권장 워크플로우
1. `linear_get_viewer`로 연결 확인
2. `linear_list_issues`/`linear_search_issues`로 대상 조회
3. 필요 시 `linear_create_issue` 실행

## 참고 문서
- https://linear.app/developers/graphql
- https://linear.app/developers/oauth-2-0-authentication

