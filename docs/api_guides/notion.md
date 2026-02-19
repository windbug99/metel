# Notion API Guide (metel)

## 1. 목적

- Notion 연동 작업(조회/생성/업데이트)을 안정적으로 수행하기 위한 운영 기준 문서다.
- 에이전트는 본 문서를 참고해 계획을 수립하되, 실제 실행 가능한 도구는 `backend/agent/tool_specs/notion.json`으로 제한한다.

## 2. 인증

- OAuth 2.0 기반(Notion Integration)
- Access token은 `oauth_tokens`에 암호화 저장
- Refresh 토큰은 Notion 정책에 따라 사용(필요 시 재인증 유도)
- 필수 헤더:
  - `Authorization: Bearer <token>`
  - `Notion-Version: <고정 버전>`
  - `Content-Type: application/json`

## 3. 권한(Scope/Capability)

- 최소 권한:
  - 콘텐츠 읽기(Read content)
  - 콘텐츠 업데이트(Update content)
  - 콘텐츠 삽입(Insert content)
- 쓰기 작업은 사용자가 연결한 워크스페이스 범위 내에서만 허용

## 4. 핵심 엔드포인트

### 4.1 Read

- Search: `POST /v1/search`
- Retrieve page: `GET /v1/pages/{page_id}`
- Retrieve block children: `GET /v1/blocks/{block_id}/children`
- Query data source: `POST /v1/data_sources/{data_source_id}/query`

### 4.2 Write

- Create page: `POST /v1/pages`
- Update page: `PATCH /v1/pages/{page_id}`
- Append block children: `PATCH /v1/blocks/{block_id}/children`
- Delete block/archive: `DELETE /v1/blocks/{block_id}`

## 5. 제한 사항

- Notion API rate limit 준수 필요(429 발생 가능)
- 블록/페이지 페이로드 크기 제한 고려 필요
- 검색 결과, 블록 children 응답은 pagination 대응 필요
- 쓰기 작업은 idempotency 키 또는 중복 방지 로직 권장

## 6. 에러 처리

- 401/403: 토큰 만료 또는 권한 부족 → 재연동 안내
- 404: 페이지/블록 접근 불가 또는 ID 오류
- 429: backoff 재시도
- 5xx: 제한 횟수 재시도 후 실패 반환

## 7. 권장 워크플로우

1. 최근 페이지 요약 후 회의록 생성  
   `search -> retrieve children -> summarize -> create page -> append blocks`
2. 특정 키워드 페이지 검색 후 액션 아이템 추가  
   `search -> retrieve page -> append blocks`
3. 기존 페이지 상태 업데이트  
   `retrieve page -> patch page`

## 8. 테스트 체크리스트

- [ ] Search 동작 확인
- [ ] Page/Block 조회 확인
- [ ] 새 페이지 생성 확인
- [ ] 401/403/429 에러 핸들링 확인

## 9. 참고 문서

- https://developers.notion.com/reference/intro
- https://developers.notion.com/reference/post-search
- https://developers.notion.com/reference/post-page
- https://developers.notion.com/reference/get-block-children
