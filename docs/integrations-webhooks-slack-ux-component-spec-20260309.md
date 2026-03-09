# Integrations/Webhooks Slack UX Component Spec (2026-03-09)

## Scope
- Target page: `frontend/app/dashboard/(v2)/integrations/webhooks/page.tsx`
- Goal: Replace raw webhook form UX with provider-driven Slack setup flow.
- This document defines component hierarchy, props interfaces, and state/event contracts.

## Component Tree
```tsx
<WebhooksPageShell>
  <WebhookProviderPicker />
  <WebhookSetupWizard>
    <ProviderGuideCard />      // SlackGuideCard when provider=slack
    <WebhookConnectionForm>
      <WebhookUrlInputWithValidation />
      <WebhookEventPresetSelector />
      <WebhookEventChipsEditor />
      <WebhookTestPanel />
    </WebhookConnectionForm>
  </WebhookSetupWizard>
  <WebhookConnectionsList />
  <WebhookDeliveriesPanel />
</WebhooksPageShell>
```

## Types
```ts
export type WebhookProvider = "slack" | "discord" | "teams" | "generic";

export type WebhookEventType =
  | "tool_called"
  | "tool_succeeded"
  | "tool_failed"
  | "policy_blocked"
  | "quota_exceeded"
  | "access_denied";

export type UrlValidationResult = {
  valid: boolean;
  message: string;
  normalizedUrl?: string;
};

export type WebhookDraft = {
  provider: WebhookProvider;
  name: string;
  endpointUrl: string;
  secret: string;
  eventTypes: WebhookEventType[];
  templateId: string | null;
};

export type WebhookTestResult = {
  ok: boolean;
  httpStatus: number | null;
  latencyMs: number | null;
  message: string;
  verifiedAt?: string;
};

export type ExistingWebhook = {
  id: number;
  provider: WebhookProvider;
  name: string;
  endpointUrlMasked: string;
  eventTypes: WebhookEventType[];
  isActive: boolean;
  lastSuccessAt: string | null;
  lastFailureAt: string | null;
  lastErrorMessage: string | null;
};
```

## Props Interfaces
```ts
export type WebhookProviderPickerProps = {
  value: WebhookProvider;
  disabled?: boolean;
  onChange: (provider: WebhookProvider) => void;
};

export type ProviderGuideCardProps = {
  provider: WebhookProvider;
  completed: boolean;
  disabled?: boolean;
  onCompletedChange: (completed: boolean) => void;
  onOpenExternal: (url: string) => void;
};

export type WebhookConnectionFormProps = {
  draft: WebhookDraft;
  canManage: boolean;
  saving: boolean;
  guideCompleted: boolean;
  validation: UrlValidationResult;
  testResult: WebhookTestResult | null;
  onDraftChange: (patch: Partial<WebhookDraft>) => void;
  onSendTest: () => Promise<void>;
  onSave: () => Promise<void>;
};

export type WebhookUrlInputWithValidationProps = {
  provider: WebhookProvider;
  value: string;
  disabled?: boolean;
  validation: UrlValidationResult;
  onChange: (next: string) => void;
  onBlur?: () => void;
};

export type WebhookEventPreset = {
  id: string;
  label: string;
  description: string;
  events: WebhookEventType[];
};

export type WebhookEventPresetSelectorProps = {
  provider: WebhookProvider;
  presets: WebhookEventPreset[];
  selectedPresetId: string | null;
  disabled?: boolean;
  onSelectPreset: (presetId: string) => void;
};

export type WebhookEventChipsEditorProps = {
  value: WebhookEventType[];
  availableEvents: WebhookEventType[];
  disabled?: boolean;
  onChange: (next: WebhookEventType[]) => void;
};

export type WebhookTestPanelProps = {
  provider: WebhookProvider;
  pending: boolean;
  result: WebhookTestResult | null;
  disabled?: boolean;
  onSendTest: () => Promise<void>;
};

export type WebhookConnectionsListProps = {
  items: ExistingWebhook[];
  canManage: boolean;
  busyId: number | null;
  onEdit: (id: number) => void;
  onToggleActive: (id: number, nextActive: boolean) => Promise<void>;
  onSendTest: (id: number) => Promise<void>;
};

export type WebhookDeliveriesPanelProps = {
  items: Array<{
    id: number;
    subscriptionId: number;
    eventType: string;
    status: string;
    httpStatus: number | null;
    errorMessage: string | null;
    retryCount: number;
    nextRetryAt: string | null;
    createdAt: string;
  }>;
  canManage: boolean;
  retryingId: number | null;
  processingRetries: boolean;
  onRetryOne: (id: number) => Promise<void>;
  onProcessRetries: () => Promise<void>;
};
```

## Slack-Specific Rules
- URL validation regex: `^https://hooks\\.slack\\.com/services/[^/]+/[^/]+/[^/]+$`
- `required`: `name`, `endpointUrl`, at least 1 `eventType`
- Save button enabled when all are true:
  - `canManage`
  - `guideCompleted`
  - `validation.valid`
  - `eventTypes.length > 0`
- Recommended: require successful test before save in org production mode.

## Suggested State Model (Page Container)
```ts
type WebhookUxState = {
  draft: WebhookDraft;
  guideCompleted: boolean;
  validation: UrlValidationResult;
  testing: boolean;
  testResult: WebhookTestResult | null;
  saving: boolean;
  error: string | null;
};
```

## Integration Notes for Existing Page
- Keep existing fetch/create/retry APIs and wrap them with adapter functions.
- Replace direct `Input` controls with `WebhookConnectionForm`.
- Map current backend payload to `WebhookDraft` before save:
  - `endpoint_url <- draft.endpointUrl`
  - `secret <- draft.secret || null`
  - `event_types <- draft.eventTypes`
  - Add `provider` field when backend is extended.

## Minimum Implementation Sequence
1. Introduce `WebhookProviderPicker` + `SlackGuideCard`.
2. Add `WebhookUrlInputWithValidation` and form-level button gating.
3. Add `WebhookTestPanel` and connect test API.
4. Refactor existing list/delivery panels to separated components.
