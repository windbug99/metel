# metel User Guide Source

This document is the source of truth for the dashboard User Guide page.
The page parser reads this file and renders content automatically.

## Language Sections
- `### [en]` for English
- `### [ko]` for Korean

---

### [en]

#### meta
- title: User Guide
- tooltip: Step-by-step onboarding guide for Organization, Team, and User setup.
- contents_label: Contents
- quick_start_label: Quick Start
- quick_start_text: Recommended order: Organization baseline setup -> Team policy and API key rollout -> User security and OAuth setup -> Usage and audit checks.
- org_setup_label: Organization Setup
- team_setup_label: Team Setup
- user_setup_label: User Setup
- menu_reference_label: Menu Reference
- faq_label: Ops / FAQ
- show_label: Show
- hide_label: Hide

#### organization_setup

##### Step O-1. Create Organization
- menu: Organization > Organizations
- menu_href: /dashboard/access/organizations
- what: Create the base operating unit for governance and ownership.
- values: Organization name should clearly identify legal entity or business unit.
- why: Teams, memberships, policies, integrations, and audit controls are scoped by organization.
- done: Organization appears in list and can be selected as current scope.
- caution: Separate production and test organizations clearly, for example by suffix.

##### Step O-2. Invite Admin and Members
- menu: Organization > Organizations
- menu_href: /dashboard/access/organizations
- what: Invite operating admins and initial members.
- values: Invite email, role, and invite expiration window.
- why: Reduces single-owner risk and distributes daily operations.
- done: At least one admin has accepted invite and can operate independently.
- caution: Avoid over-assigning admin role and keep role-change rationale auditable.

##### Step O-3. Finalize Role Model
- menu: Organization > Organizations
- menu_href: /dashboard/access/organizations
- what: Define clear responsibility boundaries for owner, admin, and member.
- values: Role matrix with allowed actions and review responsibilities.
- why: Prevents confusion between UI visibility and actual API execution rights.
- done: Team shares and follows an approved role matrix.
- caution: Keep owner role limited to minimal required users.

##### Step O-4. Configure OAuth Governance
- menu: Organization > OAuth Governance
- menu_href: /dashboard/integrations/oauth
- what: Control allowed and required OAuth providers for the organization.
- values: Allowed providers list and required providers list.
- why: Enforces secure and consistent connection policy across users.
- done: Policy saved and violation status is visible.
- caution: Overly strict required-provider policy can block onboarding.

##### Step O-5. Configure Audit Settings
- menu: Organization > Audit Settings
- menu_href: /dashboard/control/audit-settings
- what: Define retention and collection level for audit data.
- values: Retention period and event collection level/category.
- why: Required for incident investigation, traceability, and compliance evidence.
- done: Policy persisted and reflected in current settings view.
- caution: Do not set retention too short for your compliance requirements.

##### Step O-6. Maintain Organization Settings
- menu: Organization > Organizations
- menu_href: /dashboard/access/organizations
- what: Perform rename and controlled deletion operations for organization lifecycle.
- values: New organization name for rename, exact organization name for deletion confirmation.
- why: Maintains clean organization inventory and safe decommissioning.
- done: Rename is reflected or deletion completes with guard checks.
- caution: Deletion is owner-only and removes related organization-scoped records.

#### team_setup

##### Step T-1. Create Teams and Assign Members
- menu: Team > Team Policy
- menu_href: /dashboard/access/team-policy
- what: Create team operating boundaries under the selected organization.
- values: Team name, description, and team member roles.
- why: Team-level policy, keys, and audit flows depend on team scope.
- done: Target teams exist and member assignments are complete.
- caution: Ensure each team has at least one operational owner/admin.

##### Step T-2. Author Team Policy
- menu: Team > Team Policy
- menu_href: /dashboard/access/team-policy
- what: Define team-level allowed tools and restricted actions.
- values: Policy metadata and policy rule payload.
- why: Enforces least-privilege controls tailored to team operations.
- done: Policy revision is saved and visible in history.
- caution: Team policy cannot weaken organization baseline.

##### Step T-3. Validate with Policy Simulator
- menu: Team > Policy Simulator
- menu_href: /dashboard/control/policy-simulator
- what: Test allow/deny results before policy rollout.
- values: API key, tool name, and representative argument payload.
- why: Prevents production outages from unexpected denials.
- done: Critical scenarios match expected allow or deny outcomes.
- caution: Use real operational scenarios, not synthetic-only samples.

##### Step T-4. Issue and Rotate API Keys
- menu: Team > API Keys
- menu_href: /dashboard/access/api-keys
- what: Manage key lifecycle for service integrations.
- values: Key name, allowed tools, expiration time, and metadata.
- why: Reduces blast radius from credential leaks and over-permission.
- done: Key works in test call and rotation schedule is documented.
- caution: Never share plaintext keys in chat or docs.

##### Step T-5. Run Usage and Audit Monitoring
- menu: Team > Usage
- menu_href: /dashboard/control/mcp-usage
- what: Track usage trends, failures, and audit events regularly.
- values: Time window and user or tool filters.
- why: Detect anomalies early and shorten incident response time.
- done: Baseline metrics and review cadence are defined.
- caution: If anomalies appear, review policy, keys, and OAuth state together.

#### user_setup

##### Step U-1. Configure Profile
- menu: User > Profile
- menu_href: /dashboard/profile
- what: Set clear user identity information.
- values: Display name and profile defaults.
- why: Improves accountability in logs and collaboration contexts.
- done: User can be uniquely identified by team operators.
- caution: Follow naming conventions used in your organization.

##### Step U-2. Strengthen Security
- menu: User > Security
- menu_href: /dashboard/security
- what: Apply account-level security controls.
- values: Password update and supported authentication settings.
- why: User account compromise can cascade to organization risk.
- done: Security policy requirements are satisfied.
- caution: Review active sessions on shared or temporary devices.

##### Step U-3. Connect OAuth Providers
- menu: User > OAuth Connections
- menu_href: /dashboard/integrations/oauth
- what: Connect required providers for user-context tool execution.
- values: Provider connect or disconnect operations.
- why: Enables stable execution for provider-backed tools such as Notion, Linear, GitHub, and Canva.
- done: Required providers are connected and healthy.
- caution: Disconnect unused providers to reduce exposure.

##### Step U-4. Track My Requests
- menu: User > My Requests
- menu_href: /dashboard/requests
- what: Monitor request approval and processing state.
- values: Status and date filters.
- why: Prevents missed approvals and delayed access changes.
- done: Pending and completed requests are actively tracked.
- caution: Keep request reasons clear and auditable.

#### menu_reference

##### Organization > Organizations
- menu_href: /dashboard/access/organizations
- what: Manage organizations, memberships, invites, role requests, and settings.
- values: Organization name, user identifier, invite email, and role fields.
- why: Central source for organization ownership and access boundaries.

##### Organization > Integrations
- menu_href: /dashboard/integrations/webhooks
- what: Configure webhooks and delivery targets.
- values: Endpoint URL, event type selection, and verification secret.
- why: Enables controlled automation to external systems.

###### Connecting Slack
Slack is the most common webhook delivery target. Follow these steps to connect:

1. **Create a Slack App** — Go to [api.slack.com/apps](https://api.slack.com/apps) and click "Create New App" > "From scratch". Choose your workspace.
2. **Enable Incoming Webhooks** — In the app settings, navigate to Features > Incoming Webhooks and toggle it ON.
3. **Add a Webhook to Workspace** — Click "Add New Webhook to Workspace", select the target channel (e.g. `#metel-alerts`), and authorize. Copy the generated Webhook URL (format: `https://hooks.slack.com/services/T.../B.../xxx`).
4. **Register in metel** — Go to Organization > Integrations in the metel dashboard. Click "Create Webhook" and paste the Slack Webhook URL as the Endpoint URL.
5. **Select Events** — Choose which events to forward. Recommended for operations:
   - `tool_call.failed` — execution failures
   - `policy.denied` — policy-blocked requests
   - `dead_letter.created` — repeated failure alerts
   - `access.denied` — RBAC access denial events
   - `audit.export.completed` — audit export completion
6. **Set Verification Secret** (optional) — Add a shared secret to verify webhook payloads. metel signs deliveries with `X-Metel-Signature` header using HMAC-SHA256.
7. **Test Delivery** — Click "Send Test" in the webhook detail view. Confirm the test message arrives in the target Slack channel.
8. **Monitor Deliveries** — Use the Deliveries tab to track delivery status. Failed deliveries can be retried individually or in batch.

Troubleshooting:
- If test delivery fails with timeout, confirm the Slack Webhook URL is valid and the Slack App is installed in the workspace.
- If messages arrive but content is empty, verify the selected event types match actual system activity.
- Slack Webhook URLs do not expire, but Slack Apps can be uninstalled. If deliveries suddenly fail, check Slack App status first.

##### Organization > OAuth Governance
- menu_href: /dashboard/integrations/oauth
- what: Define provider-level governance policy.
- values: Allowed provider list and required provider list.
- why: Enforces standardized external connection policy.

##### Organization > Audit Settings
- menu_href: /dashboard/control/audit-settings
- what: Configure audit retention and event policy.
- values: Retention period and category-level controls.
- why: Supports compliance and forensic investigations.

##### Team > Team Policy
- menu_href: /dashboard/access/team-policy
- what: Manage team policy revisions and team-level governance.
- values: Team metadata and policy payload.
- why: Applies least-privilege controls at team scope.

##### Team > API Keys
- menu_href: /dashboard/access/api-keys
- what: Create, rotate, and revoke team keys.
- values: Key name, allowed tools, expiry, and optional metadata.
- why: Controls machine-to-machine access safely.

##### Team > Policy Simulator
- menu_href: /dashboard/control/policy-simulator
- what: Simulate policy outcome before rollout.
- values: API key, tool, and argument payload.
- why: Reduces production policy misconfiguration risk.

##### Team > Usage / Audit Events
- menu_href: /dashboard/control/mcp-usage
- what: Monitor usage trend and audit trail.
- values: Time range and filter dimensions.
- why: Maintains operational reliability and governance visibility.

##### User > Security / OAuth / My Requests
- menu_href: /dashboard/security
- what: Manage personal security, connection state, and request tracking.
- values: Security controls, provider links, and request filters.
- why: Keeps user-level posture secure and operational.

#### faq

##### Q: Why is a menu missing?
- a: Verify your role and current scope first. Some menus are intentionally hidden based on access control.

##### Q: Why does tool execution fail even with an API key?
- a: Check allowed tools, key expiration, OAuth connection state, and policy denials in order.

##### Q: Why is Team data empty?
- a: Team scope requires valid organization and team selection. Re-select scope values and reload.

##### Q: How do I receive metel alerts in Slack?
- a: Create a Slack App with Incoming Webhooks enabled, copy the Webhook URL, and register it in Organization > Integrations. Select relevant event types (e.g. tool_call.failed, dead_letter.created) and click Send Test to verify. See the Connecting Slack section in the Integrations menu reference for step-by-step instructions.

##### Q: Slack webhook deliveries are failing. What should I check?
- a: (1) Verify the Slack Webhook URL is still valid at api.slack.com/apps. (2) Confirm the Slack App is installed and the target channel exists. (3) Check the Deliveries tab in metel for specific error codes. (4) Try the Send Test button to isolate whether the issue is metel-side or Slack-side.

---

### [ko]

#### meta
- title: 사용자 가이드
- tooltip: Organization, Team, User 설정을 단계별로 안내하는 온보딩 가이드입니다.
- contents_label: 목차
- quick_start_label: 빠른 시작
- quick_start_text: 권장 순서: Organization 기준선 설정 -> Team 정책과 API Key 배포 -> User 보안과 OAuth 설정 -> Usage 및 Audit 점검.
- org_setup_label: Organization 설정
- team_setup_label: Team 설정
- user_setup_label: User 설정
- menu_reference_label: 메뉴 상세 가이드
- faq_label: 운영 / FAQ
- show_label: 보기
- hide_label: 접기

#### organization_setup

##### Step O-1. Organization 생성
- menu: Organization > Organizations
- menu_href: /dashboard/access/organizations
- what: 거버넌스와 소유권 관리를 위한 기본 운영 단위를 생성합니다.
- values: 실제 조직이나 사업 단위를 식별할 수 있는 조직명 입력.
- why: 팀, 멤버십, 정책, 연동, 감사 설정이 Organization 스코프에 귀속됩니다.
- done: 조직 목록에 생성되고 현재 범위로 선택할 수 있습니다.
- caution: 운영 조직과 테스트 조직은 이름 규칙으로 명확히 분리하세요.

##### Step O-2. Admin/Member 초대
- menu: Organization > Organizations
- menu_href: /dashboard/access/organizations
- what: 운영 담당 admin과 초기 member를 초대합니다.
- values: 초대 이메일, 역할, 만료시간 설정.
- why: Owner 1인 체계를 피하고 운영 책임을 분산합니다.
- done: 최소 1명의 admin이 초대를 수락해 운영 가능합니다.
- caution: admin 역할 과다 부여를 피하고 변경 사유를 남기세요.

##### Step O-3. 권한 모델 확정
- menu: Organization > Organizations
- menu_href: /dashboard/access/organizations
- what: owner, admin, member 역할 경계를 확정합니다.
- values: 역할 매트릭스 문서와 실행 권한 규칙.
- why: 화면 노출 권한과 API 실행 권한 불일치를 줄입니다.
- done: 승인된 역할 매트릭스를 팀이 공유하고 준수합니다.
- caution: owner 권한은 최소 인원에게만 부여하세요.

##### Step O-4. OAuth Governance 설정
- menu: Organization > OAuth Governance
- menu_href: /dashboard/integrations/oauth
- what: 조직 차원의 허용 및 필수 OAuth provider를 관리합니다.
- values: Allowed provider 목록, Required provider 목록.
- why: 사용자별 연결 편차를 줄이고 연결 정책을 표준화합니다.
- done: 정책 저장 후 위반 상태를 확인할 수 있습니다.
- caution: 필수 provider를 과도하게 강제하면 온보딩이 지연됩니다.

##### Step O-5. Audit Settings 설정
- menu: Organization > Audit Settings
- menu_href: /dashboard/control/audit-settings
- what: 감사 데이터 보존 기간과 수집 수준을 설정합니다.
- values: 보존 기간, 이벤트 카테고리 또는 수준.
- why: 사고 분석, 추적성, 컴플라이언스 증빙에 필요합니다.
- done: 저장 후 현재 설정에 반영됩니다.
- caution: 규정 대비 보존 기간을 지나치게 짧게 설정하지 마세요.

##### Step O-6. Organization Settings 유지보수
- menu: Organization > Organizations
- menu_href: /dashboard/access/organizations
- what: 조직명 변경과 안전한 조직 삭제 절차를 운영합니다.
- values: Rename용 새 조직명, Delete용 조직명 확인 입력.
- why: 조직 목록 정합성과 안전한 폐기 절차를 유지합니다.
- done: 이름 변경 반영 또는 검증 조건을 만족한 삭제 완료.
- caution: 삭제는 owner 전용이며 관련 조직 데이터가 함께 제거됩니다.

#### team_setup

##### Step T-1. Team 생성 및 멤버 배치
- menu: Team > Team Policy
- menu_href: /dashboard/access/team-policy
- what: 선택된 Organization 아래 팀 운영 경계를 생성합니다.
- values: 팀명, 설명, 멤버 역할 지정.
- why: 팀 단위 정책, 키, 감사 흐름이 팀 스코프에 의존합니다.
- done: 대상 팀 생성 및 멤버 배치 완료.
- caution: 각 팀에 최소 1명 이상의 운영 관리자 지정.

##### Step T-2. Team Policy 작성
- menu: Team > Team Policy
- menu_href: /dashboard/access/team-policy
- what: 팀 단위 허용 도구와 제한 액션 규칙을 정의합니다.
- values: 정책 메타데이터와 정책 페이로드.
- why: 팀 운영 특성에 맞춘 최소권한 통제를 적용합니다.
- done: 정책 revision 저장 및 이력 확인 가능.
- caution: Team 정책은 Organization 기준선보다 완화할 수 없습니다.

##### Step T-3. Policy Simulator 검증
- menu: Team > Policy Simulator
- menu_href: /dashboard/control/policy-simulator
- what: 배포 전 허용 및 차단 결과를 시뮬레이션합니다.
- values: API Key, Tool 이름, 대표 인자(JSON).
- why: 정책 오설정으로 인한 운영 장애를 사전 차단합니다.
- done: 핵심 시나리오가 기대 결과와 일치합니다.
- caution: 실제 운영 시나리오 기반으로 검증하세요.

##### Step T-4. API Key 생성 및 회전
- menu: Team > API Keys
- menu_href: /dashboard/access/api-keys
- what: 팀 연동용 키의 수명주기를 관리합니다.
- values: Key 이름, 허용 도구, 만료 시점, 메타데이터.
- why: 키 유출과 과권한 리스크를 줄입니다.
- done: 테스트 호출 성공 및 회전 일정 문서화.
- caution: 평문 키를 채팅이나 문서에 노출하지 마세요.

##### Step T-5. Usage 및 Audit 모니터링
- menu: Team > Usage
- menu_href: /dashboard/control/mcp-usage
- what: 사용량 추세, 실패율, 감사 이벤트를 정기 점검합니다.
- values: 기간 범위와 사용자 또는 도구 필터.
- why: 이상 징후를 조기에 탐지하고 대응 시간을 단축합니다.
- done: 기준선 지표와 점검 주기가 정의됩니다.
- caution: 이상 징후 시 정책, 키, OAuth 상태를 함께 점검하세요.

#### user_setup

##### Step U-1. Profile 설정
- menu: User > Profile
- menu_href: /dashboard/profile
- what: 사용자 식별 정보를 명확하게 설정합니다.
- values: 표시명과 기본 프로필 값.
- why: 로그 추적성과 협업 정확도를 높입니다.
- done: 운영자가 사용자 식별을 명확히 할 수 있습니다.
- caution: 조직 내 네이밍 규칙을 따르세요.

##### Step U-2. Security 강화
- menu: User > Security
- menu_href: /dashboard/security
- what: 계정 보안 제어를 적용합니다.
- values: 비밀번호 변경과 지원되는 인증 설정.
- why: 사용자 계정 침해가 조직 리스크로 확산되는 것을 방지합니다.
- done: 보안 정책 기준을 충족합니다.
- caution: 공용 장비 사용 시 활성 세션을 정기 점검하세요.

##### Step U-3. OAuth 연결
- menu: User > OAuth Connections
- menu_href: /dashboard/integrations/oauth
- what: 사용자 컨텍스트 실행에 필요한 provider를 연결합니다.
- values: provider 연결 또는 해제 작업.
- why: provider 기반 도구의 안정적 실행을 보장합니다.
- done: 필수 provider 연결이 완료되고 상태가 정상입니다.
- caution: 사용하지 않는 provider는 해제해 노출면을 줄이세요.

##### Step U-4. My Requests 추적
- menu: User > My Requests
- menu_href: /dashboard/requests
- what: 권한 및 변경 요청 상태를 추적합니다.
- values: 상태 및 기간 필터.
- why: 승인 누락과 처리 지연을 방지합니다.
- done: 대기 요청과 완료 요청을 지속적으로 관리합니다.
- caution: 요청 사유는 감사 가능한 문장으로 작성하세요.

#### menu_reference

##### Organization > Organizations
- menu_href: /dashboard/access/organizations
- what: 조직, 멤버십, 초대, 역할요청, 설정을 관리합니다.
- values: 조직명, 사용자 식별자, 초대 이메일, 역할 필드.
- why: 조직 소유권과 접근 경계의 중심 메뉴입니다.

##### Organization > Integrations
- menu_href: /dashboard/integrations/webhooks
- what: Webhook 대상과 전송 설정을 관리합니다.
- values: Endpoint URL, 이벤트 선택, 검증용 시크릿.
- why: 외부 시스템 자동화 연동을 안전하게 운영합니다.

###### Slack 연결 방법
Slack은 가장 많이 사용되는 Webhook 전송 대상입니다. 아래 절차를 따라 연결하세요:

1. **Slack App 생성** — [api.slack.com/apps](https://api.slack.com/apps) 에서 "Create New App" > "From scratch"를 선택합니다. 대상 워크스페이스를 지정합니다.
2. **Incoming Webhooks 활성화** — 앱 설정에서 Features > Incoming Webhooks 로 이동하여 토글을 ON으로 변경합니다.
3. **워크스페이스에 Webhook 추가** — "Add New Webhook to Workspace"를 클릭하고 수신 채널(예: `#metel-alerts`)을 선택한 후 승인합니다. 생성된 Webhook URL(형식: `https://hooks.slack.com/services/T.../B.../xxx`)을 복사합니다.
4. **metel에 등록** — metel 대시보드에서 Organization > Integrations 로 이동합니다. "Create Webhook"을 클릭하고 Slack Webhook URL을 Endpoint URL에 붙여넣습니다.
5. **이벤트 선택** — 전달할 이벤트를 선택합니다. 운영 권장 이벤트:
   - `tool_call.failed` — 실행 실패
   - `policy.denied` — 정책 차단 요청
   - `dead_letter.created` — 반복 실패 알림
   - `access.denied` — RBAC 접근 거부 이벤트
   - `audit.export.completed` — 감사 로그 내보내기 완료
6. **Verification Secret 설정** (선택) — 공유 시크릿을 추가하면 metel이 `X-Metel-Signature` 헤더에 HMAC-SHA256 서명을 포함하여 전송합니다.
7. **테스트 전송** — Webhook 상세 화면에서 "Send Test"를 클릭합니다. 대상 Slack 채널에 테스트 메시지가 도착하는지 확인합니다.
8. **전송 상태 모니터링** — Deliveries 탭에서 전송 상태를 추적합니다. 실패한 전송은 개별 또는 일괄 재시도할 수 있습니다.

트러블슈팅:
- 테스트 전송이 timeout으로 실패하면 Slack Webhook URL이 유효한지, Slack App이 워크스페이스에 설치되어 있는지 확인하세요.
- 메시지는 도착하지만 내용이 비어 있다면 선택한 이벤트 타입이 실제 시스템 활동과 일치하는지 확인하세요.
- Slack Webhook URL은 만료되지 않지만 Slack App이 제거될 수 있습니다. 전송이 갑자기 실패하면 먼저 Slack App 상태를 점검하세요.

##### Organization > OAuth Governance
- menu_href: /dashboard/integrations/oauth
- what: provider 수준의 연결 정책을 설정합니다.
- values: 허용 provider 목록, 필수 provider 목록.
- why: 조직 표준 연결 정책을 일관되게 적용합니다.

##### Organization > Audit Settings
- menu_href: /dashboard/control/audit-settings
- what: 감사 보존기간과 이벤트 정책을 정의합니다.
- values: 보존 기간과 카테고리별 제어값.
- why: 컴플라이언스와 사고 조사 대응력을 보장합니다.

##### Team > Team Policy
- menu_href: /dashboard/access/team-policy
- what: 팀 정책 revision과 팀 운영 규칙을 관리합니다.
- values: 팀 메타데이터와 정책 페이로드.
- why: 팀 단위 최소권한 통제를 적용합니다.

##### Team > API Keys
- menu_href: /dashboard/access/api-keys
- what: 팀 키 생성, 회전, 폐기를 수행합니다.
- values: 키 이름, 허용 도구, 만료, 메타데이터.
- why: 기계 계정 접근을 안전하게 관리합니다.

##### Team > Policy Simulator
- menu_href: /dashboard/control/policy-simulator
- what: 정책 배포 전 결과를 시뮬레이션합니다.
- values: API Key, Tool, 인자 페이로드.
- why: 운영 정책 오설정 위험을 줄입니다.

##### Team > Usage / Audit Events
- menu_href: /dashboard/control/mcp-usage
- what: 사용량 추세와 감사 로그를 점검합니다.
- values: 기간 범위와 필터 조건.
- why: 운영 신뢰성과 거버넌스 가시성을 유지합니다.

##### User > Security / OAuth / My Requests
- menu_href: /dashboard/security
- what: 개인 보안, 연결 상태, 요청 이력을 관리합니다.
- values: 보안 설정, provider 연결 상태, 요청 필터.
- why: 사용자 보안 상태와 업무 연속성을 유지합니다.

#### faq

##### Q: 메뉴가 보이지 않는 이유는 무엇인가요?
- a: 먼저 현재 역할과 scope를 확인하세요. 접근 제어에 따라 일부 메뉴는 숨김 처리됩니다.

##### Q: API Key가 있는데도 실행이 실패하는 이유는 무엇인가요?
- a: 허용 도구, 키 만료, OAuth 연결 상태, 정책 차단 여부를 순서대로 점검하세요.

##### Q: Team 데이터가 비어있는 이유는 무엇인가요?
- a: Team scope에는 유효한 Organization과 Team 선택이 필요합니다. 범위를 다시 선택한 후 새로고침하세요.

##### Q: metel 알림을 Slack에서 받으려면 어떻게 하나요?
- a: Incoming Webhooks이 활성화된 Slack App을 생성하고 Webhook URL을 복사한 뒤 Organization > Integrations에 등록합니다. 이벤트 타입(예: tool_call.failed, dead_letter.created)을 선택하고 Send Test로 검증하세요. 상세 절차는 Integrations 메뉴 상세 가이드의 Slack 연결 방법 섹션을 참고하세요.

##### Q: Slack webhook 전송이 실패합니다. 무엇을 점검해야 하나요?
- a: (1) api.slack.com/apps에서 Slack Webhook URL이 유효한지 확인합니다. (2) Slack App이 설치되어 있고 대상 채널이 존재하는지 확인합니다. (3) metel의 Deliveries 탭에서 구체적인 에러 코드를 확인합니다. (4) Send Test 버튼으로 metel 측인지 Slack 측인지 원인을 분리합니다.
