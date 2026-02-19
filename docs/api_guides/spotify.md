# Spotify API Guide (metel)

## 1. 목적

- Spotify 관련 요청(추천 곡 조회, 플레이리스트 생성/추가)을 일관되게 처리하기 위한 운영 기준 문서다.
- 에이전트는 본 문서를 참고해 계획을 수립하고, 실행은 `backend/agent/tool_specs/spotify.json`에 정의된 도구로 제한한다.

## 2. 인증

- OAuth 2.0 Authorization Code Flow
- Access token/refresh token을 `oauth_tokens`에 암호화 저장
- 토큰 만료 시 refresh 토큰으로 갱신
- 필수 헤더:
  - `Authorization: Bearer <token>`
  - `Content-Type: application/json`

## 3. 권한(Scope)

- 최소 권한:
  - `playlist-read-private`
  - `playlist-modify-private`
  - `playlist-modify-public`
- 선택 권한:
  - `user-top-read` (상위 트랙 기반 추천 구성 시)
  - `user-read-recently-played` (최근 재생곡 기반 자동화)

## 4. 핵심 엔드포인트

### 4.1 Read

- 현재 사용자 조회: `GET /v1/me`
- 최근 재생곡 조회: `GET /v1/me/player/recently-played`
- 툴 이름 호환성:
  - `spotify_get_recently_played` (정식)
  - `spotify_get_recent_tracks` (planner/autonomous 호환 alias)
- 사용자 상위 트랙: `GET /v1/me/top/tracks`
- 플레이리스트 트랙 조회: `GET /v1/playlists/{playlist_id}/tracks`

### 4.2 Write

- 플레이리스트 생성: `POST /v1/users/{user_id}/playlists`
- 플레이리스트 트랙 추가: `POST /v1/playlists/{playlist_id}/tracks`
- (선택) 플레이리스트 메타 업데이트: `PUT /v1/playlists/{playlist_id}`

## 5. 제한 사항

- API rate limit 존재(429 + Retry-After 대응)
- 트랙 추가는 URI 단위로 처리(배치 크기 제한 고려)
- 동일 요청 중복 실행 방지(idempotency key/중복 트랙 체크) 필요
- Spotify Web API는 가사(lyrics) 엔드포인트를 제공하지 않음
  - 구현 시나리오에서 가사는 별도 가사 소스 조회가 필요

## 6. 에러 처리

- 401: 토큰 만료/무효 → refresh 또는 재연동
- 403: scope 부족
- 429: Retry-After 기반 backoff
- 5xx: 제한 횟수 재시도 후 실패 반환

## 7. 권장 워크플로우

1. "출근용 잔잔한 플레이리스트 만들어줘"  
   `get me -> get top tracks -> create playlist -> add tracks`
2. "운동용 플레이리스트에 최근 들은 곡 10개 추가해줘"  
   `fetch source tracks -> add tracks`
3. "집중용 새 플레이리스트 만들어줘(공개)"  
   `create playlist(public=true) -> add tracks`

## 8. 테스트 체크리스트

- [ ] 사용자 정보 조회 확인
- [ ] 플레이리스트 생성 확인
- [ ] 트랙 추가 확인
- [ ] 401/403/429 에러 핸들링 확인

## 9. 참고 문서

- https://developer.spotify.com/documentation/web-api
- https://developer.spotify.com/documentation/web-api/reference/create-playlist
- https://developer.spotify.com/documentation/web-api/reference/add-tracks-to-playlist
