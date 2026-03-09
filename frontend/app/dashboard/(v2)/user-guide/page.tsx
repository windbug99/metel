"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

import PageTitleWithTooltip from "@/components/dashboard-v2/page-title-with-tooltip";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { cn } from "@/lib/utils";

type Role = "owner" | "admin" | "member";

type StepItem = {
  id: string;
  title: string;
  path: string;
  what: string;
  values: string;
  why: string;
  done: string;
  caution: string;
  roles: Role[];
};

type MenuGuideItem = {
  id: string;
  menu: string;
  what: string;
  values: string;
  why: string;
};

const SECTION_ITEMS = [
  { id: "quick-start", label: "Quick Start" },
  { id: "org-setup", label: "Organization Setup" },
  { id: "team-setup", label: "Team Setup" },
  { id: "user-setup", label: "User Setup" },
  { id: "menu-reference", label: "Menu Reference" },
  { id: "ops-faq", label: "Ops / FAQ" },
] as const;

const ORG_STEPS: StepItem[] = [
  {
    id: "o1",
    title: "Step O-1. Organization 생성",
    path: "Organization > Organizations",
    what: "조직 운영의 기준 단위를 만든다.",
    values: "Organization Name: 실제 조직 식별이 가능한 이름(예: Acme Corp)",
    why: "정책/권한/감사/팀 데이터가 Organization 단위로 귀속된다.",
    done: "목록에서 생성된 조직 확인 + 상세 진입 가능",
    caution: "운영/테스트 조직 이름을 분리(-prod, -dev).",
    roles: ["owner"],
  },
  {
    id: "o2",
    title: "Step O-2. Admin/Member 초대",
    path: "Organization > Organizations > Users/Invites",
    what: "운영 담당자와 일반 구성원을 초대한다.",
    values: "Email, Role(owner/admin/member), Invite Expiration(권장 7~14일)",
    why: "Owner 1인 체계 리스크를 줄이고 운영/감사 책임을 분리한다.",
    done: "최소 1명 이상 admin onboarding 완료",
    caution: "과도한 admin 부여 금지, 역할 변경 사유 기록.",
    roles: ["owner", "admin"],
  },
  {
    id: "o3",
    title: "Step O-3. 권한 체계 확정",
    path: "Organization > Organizations",
    what: "owner/admin/member 책임 범위를 확정한다.",
    values: "역할 매트릭스 문서화 후 실제 역할과 동기화",
    why: "UI 노출 권한과 API 실행 권한 불일치를 줄인다.",
    done: "팀 내 권한 운영 원칙 공유 완료",
    caution: "owner 승격은 최소 인원만 허용.",
    roles: ["owner"],
  },
  {
    id: "o4",
    title: "Step O-4. OAuth Governance 설정",
    path: "Organization > OAuth Governance",
    what: "허용/필수 provider 정책을 설정한다.",
    values: "Allowed Providers, Required Providers",
    why: "연결 표준을 통제하고 보안 리스크를 줄인다.",
    done: "정책 저장 + 위반 사용자 상태 확인",
    caution: "Required를 과도하게 잡지 않는다.",
    roles: ["owner", "admin"],
  },
  {
    id: "o5",
    title: "Step O-5. Audit Settings 설정",
    path: "Organization > Audit Settings",
    what: "감사 로그 보존/수집 수준을 정한다.",
    values: "Retention Days, Audit Level/Category",
    why: "사고 추적/컴플라이언스 증빙을 확보한다.",
    done: "정책 저장 후 조회값 반영 확인",
    caution: "보존기간 과소 설정 금지(권장 90일+).",
    roles: ["owner", "admin"],
  },
  {
    id: "o6",
    title: "Step O-6. Organization Settings 유지보수",
    path: "Organization > Organizations > Settings",
    what: "조직명 변경과 삭제 정책을 운영한다.",
    values: "Rename: 신규 조직명, Delete: 조직명 확인 입력",
    why: "조직 식별 명확화 및 폐기 절차 통제",
    done: "이름 변경 반영 또는 삭제 완료(권한/검증 통과)",
    caution: "Delete는 owner만 가능, 삭제 시 연관 데이터 제거됨.",
    roles: ["owner"],
  },
];

const TEAM_STEPS: StepItem[] = [
  {
    id: "t1",
    title: "Step T-1. Team 생성 및 멤버 배치",
    path: "Team > Team Policy",
    what: "팀 단위 운영 경계를 생성한다.",
    values: "Team Name, Description, Member Role",
    why: "정책/API Key/감사 이벤트를 팀 단위로 분리하기 위함",
    done: "팀 생성 + 멤버 배치 완료",
    caution: "팀 관리자 최소 1명 지정.",
    roles: ["owner", "admin"],
  },
  {
    id: "t2",
    title: "Step T-2. Team Policy 작성",
    path: "Team > Team Policy",
    what: "팀 허용 도구/행위를 정책으로 정의",
    values: "Policy Name/Version, Policy JSON(Rule)",
    why: "팀별 최소권한/운영 통제 구현",
    done: "정책 저장 + Revision 기록 생성",
    caution: "Organization baseline 완화 금지.",
    roles: ["owner", "admin"],
  },
  {
    id: "t3",
    title: "Step T-3. Policy Simulator 검증",
    path: "Team > Policy Simulator",
    what: "배포 전 허용/차단 결과 검증",
    values: "API Key, Tool Name, Arguments(JSON)",
    why: "운영 차단 사고 예방",
    done: "핵심 시나리오 결과가 기대와 일치",
    caution: "실제 운영 시나리오 기반으로 테스트.",
    roles: ["owner", "admin"],
  },
  {
    id: "t4",
    title: "Step T-4. API Key 생성/회전",
    path: "Team > API Keys",
    what: "팀 키 수명주기 관리",
    values: "Name(team-purpose-env), Allowed Tools, Expires At",
    why: "인증/권한 오남용 리스크 최소화",
    done: "키 생성 + 테스트 호출 + 회전 일정 수립",
    caution: "평문 공유 금지, 퇴사/권한변경 즉시 폐기.",
    roles: ["owner", "admin"],
  },
  {
    id: "t5",
    title: "Step T-5. Usage/Audit 운영 루틴",
    path: "Team > Usage / Audit Events",
    what: "호출량/실패율/감사 이벤트 정기 점검",
    values: "기간 필터(24h/7d), 사용자/도구/상태 필터",
    why: "장애 징후 조기 감지 및 원인 분석",
    done: "팀 기준선 문서화 + 주기 점검 루틴 확정",
    caution: "이상치 발견 시 정책/키/OAuth 동시 점검.",
    roles: ["owner", "admin", "member"],
  },
];

const USER_STEPS: StepItem[] = [
  {
    id: "u1",
    title: "Step U-1. Profile 설정",
    path: "User > Profile",
    what: "표시명/기본 정보 점검",
    values: "표시명, 개인 기본값",
    why: "감사 로그/협업 시 사용자 식별 정확도 향상",
    done: "팀이 사용자 식별 가능",
    caution: "조직 표기 규칙과 일치시킬 것.",
    roles: ["owner", "admin", "member"],
  },
  {
    id: "u2",
    title: "Step U-2. Security 강화",
    path: "User > Security",
    what: "계정 보안 설정 강화",
    values: "비밀번호, 인증/세션 설정",
    why: "계정 탈취 리스크 최소화",
    done: "보안 정책 준수 상태 확인",
    caution: "공용 디바이스 로그인 세션 점검.",
    roles: ["owner", "admin", "member"],
  },
  {
    id: "u3",
    title: "Step U-3. OAuth 연결",
    path: "User > OAuth Connections",
    what: "업무에 필요한 Provider 연결",
    values: "Provider별 Connect/Disconnect",
    why: "사용자 컨텍스트 도구 사용 보장",
    done: "필수 provider 연결 완료",
    caution: "불필요 연결은 해제 유지.",
    roles: ["owner", "admin", "member"],
  },
  {
    id: "u4",
    title: "Step U-4. My Requests 점검",
    path: "User > My Requests",
    what: "권한/변경 요청 상태 추적",
    values: "상태/기간 필터",
    why: "처리 지연/누락을 빠르게 파악",
    done: "미처리 요청 식별 및 후속 조치",
    caution: "요청 사유는 감사 가능한 문장으로 작성.",
    roles: ["owner", "admin", "member"],
  },
];

const MENU_GUIDES: MenuGuideItem[] = [
  {
    id: "m1",
    menu: "Organization > Organizations",
    what: "조직/멤버/초대/역할요청/Settings 관리",
    values: "조직명, 사용자 ID, 이메일, 역할(role)",
    why: "조직 책임 경계와 접근권한을 명확히 유지",
  },
  {
    id: "m2",
    menu: "Organization > Integrations",
    what: "Webhook 엔드포인트와 전송 이벤트 관리",
    values: "Endpoint URL(https), Event Type, Secret",
    why: "외부 시스템 자동화 연동",
  },
  {
    id: "m3",
    menu: "Organization > OAuth Governance",
    what: "provider 허용/필수 정책 관리",
    values: "Allowed Providers, Required Providers",
    why: "조직 보안 표준과 연결 정책 일관성 유지",
  },
  {
    id: "m4",
    menu: "Organization > Audit Settings",
    what: "감사 보존/수집 강도 설정",
    values: "Retention, Level/Category",
    why: "감사 추적성과 컴플라이언스 보장",
  },
  {
    id: "m5",
    menu: "Team > Team Policy",
    what: "팀 정책 및 멤버 운영",
    values: "Policy JSON/Rule, 팀명, 멤버 역할",
    why: "팀별 최소권한 운영",
  },
  {
    id: "m6",
    menu: "Team > API Keys",
    what: "키 생성/회전/폐기",
    values: "Name, Allowed Tools, Expiration",
    why: "인증키 오남용 및 유출 대응",
  },
  {
    id: "m7",
    menu: "Team > Policy Simulator",
    what: "정책 결과 사전 검증",
    values: "API Key, Tool, Arguments(JSON)",
    why: "배포 전 차단 사고 예방",
  },
  {
    id: "m8",
    menu: "Team > Usage / Audit Events",
    what: "사용량/감사 이벤트 분석",
    values: "기간/상태/사용자/도구 필터",
    why: "운영 품질 모니터링",
  },
  {
    id: "m9",
    menu: "User > Security / OAuth / My Requests",
    what: "개인 보안/연결/요청 관리",
    values: "보안 설정, provider 연결 상태, 요청 상태",
    why: "개인 계정 안전성과 작업 연속성 유지",
  },
];

const FAQ_ITEMS = [
  {
    q: "메뉴가 보이지 않습니다.",
    a: "현재 역할과 scope(org/team/user)를 먼저 확인하세요. 권한이 없는 메뉴는 노출되지 않습니다.",
  },
  {
    q: "API Key가 있는데 호출이 실패합니다.",
    a: "Allowed Tools, 만료 상태, OAuth 연결, Organization/Team 정책 차단 여부를 순서대로 점검하세요.",
  },
  {
    q: "Team 데이터가 비어있습니다.",
    a: "scope=team 에 필요한 org/team 선택값이 없는 경우입니다. Organization/Team을 다시 선택하세요.",
  },
] as const;

function StepCard({ item }: { item: StepItem }) {
  return (
    <article className="rounded-md border border-border bg-card p-4">
      <p className="text-sm font-semibold">{item.title}</p>
      <p className="mt-1 text-xs text-muted-foreground">경로: {item.path}</p>
      <div className="mt-3 space-y-2 text-sm">
        <p><span className="font-medium">무엇:</span> {item.what}</p>
        <p><span className="font-medium">입력값:</span> {item.values}</p>
        <p><span className="font-medium">왜:</span> {item.why}</p>
        <p><span className="font-medium">완료 기준:</span> {item.done}</p>
        <p className="text-muted-foreground"><span className="font-medium">실수 방지:</span> {item.caution}</p>
      </div>
    </article>
  );
}

export default function DashboardUserGuidePage() {
  const [roleFilter, setRoleFilter] = useState<Role | "all">("all");
  const [openMenus, setOpenMenus] = useState<Record<string, boolean>>(
    Object.fromEntries(MENU_GUIDES.map((item) => [item.id, false]))
  );

  const filterByRole = (items: StepItem[]) => {
    if (roleFilter === "all") {
      return items;
    }
    return items.filter((item) => item.roles.includes(roleFilter));
  };

  const orgSteps = useMemo(() => filterByRole(ORG_STEPS), [roleFilter]);
  const teamSteps = useMemo(() => filterByRole(TEAM_STEPS), [roleFilter]);
  const userSteps = useMemo(() => filterByRole(USER_STEPS), [roleFilter]);

  const expandAllMenus = () => {
    setOpenMenus(Object.fromEntries(MENU_GUIDES.map((item) => [item.id, true])));
  };

  const collapseAllMenus = () => {
    setOpenMenus(Object.fromEntries(MENU_GUIDES.map((item) => [item.id, false])));
  };

  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <PageTitleWithTooltip
          title="User Guide"
          tooltip="초기 구축부터 운영 점검까지, Organization/Team/User 기준으로 따라하는 가이드입니다."
        />
        <div className="flex items-center gap-2">
          <Button type="button" variant="outline" className="h-8 px-3 text-xs" onClick={() => window.scrollTo({ top: 0, behavior: "smooth" })}>
            처음부터 보기
          </Button>
          <Button type="button" variant="outline" className="h-8 px-3 text-xs" onClick={expandAllMenus}>
            전체 펼치기
          </Button>
          <Button type="button" variant="outline" className="h-8 px-3 text-xs" onClick={collapseAllMenus}>
            전체 접기
          </Button>
        </div>
      </div>

      <div className="ds-card p-4" id="quick-start">
        <p className="text-sm font-semibold">Quick Start</p>
        <p className="mt-1 text-sm text-muted-foreground">
          권장 순서: Organization baseline 설정 → Team 정책/키 배포 → User 개인 보안/연결 설정 → Usage/Audit 점검
        </p>
        <div className="mt-3 grid gap-2 md:grid-cols-2">
          <div>
            <p className="mb-1 text-xs text-muted-foreground">역할 필터</p>
            <Select
              value={roleFilter}
              onChange={(event) => setRoleFilter(event.target.value as Role | "all")}
              className="ds-input h-9 w-full rounded-md px-3 text-sm"
            >
              <option value="all">All roles</option>
              <option value="owner">Owner</option>
              <option value="admin">Admin</option>
              <option value="member">Member</option>
            </Select>
          </div>
          <div className="rounded-md border border-border bg-background p-3 text-xs text-muted-foreground">
            역할 필터를 적용하면 해당 역할에서 필요한 단계만 노출됩니다.
          </div>
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-[220px,1fr]">
        <aside className="hidden lg:block">
          <nav className="sticky top-4 rounded-md border border-border bg-card p-3">
            <p className="mb-2 text-xs font-medium text-muted-foreground">Contents</p>
            <div className="space-y-1">
              {SECTION_ITEMS.map((section) => (
                <a
                  key={section.id}
                  href={`#${section.id}`}
                  className="block rounded px-2 py-1 text-sm text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground"
                >
                  {section.label}
                </a>
              ))}
            </div>
          </nav>
        </aside>

        <div className="space-y-4">
          <div className="lg:hidden">
            <Select
              defaultValue="quick-start"
              onChange={(event) => {
                const target = document.getElementById(event.target.value);
                if (target) {
                  target.scrollIntoView({ behavior: "smooth", block: "start" });
                }
              }}
              className="ds-input h-9 w-full rounded-md px-3 text-sm"
            >
              {SECTION_ITEMS.map((section) => (
                <option key={section.id} value={section.id}>
                  {section.label}
                </option>
              ))}
            </Select>
          </div>

          <div id="org-setup" className="space-y-3">
            <p className="text-lg font-semibold">Organization Setup</p>
            {orgSteps.map((item) => (
              <StepCard key={item.id} item={item} />
            ))}
          </div>

          <div id="team-setup" className="space-y-3">
            <p className="text-lg font-semibold">Team Setup</p>
            {teamSteps.map((item) => (
              <StepCard key={item.id} item={item} />
            ))}
          </div>

          <div id="user-setup" className="space-y-3">
            <p className="text-lg font-semibold">User Setup</p>
            {userSteps.map((item) => (
              <StepCard key={item.id} item={item} />
            ))}
          </div>

          <div id="menu-reference" className="space-y-3">
            <p className="text-lg font-semibold">Menu Reference</p>
            {MENU_GUIDES.map((item) => {
              const open = Boolean(openMenus[item.id]);
              return (
                <article key={item.id} className="rounded-md border border-border bg-card">
                  <button
                    type="button"
                    onClick={() => setOpenMenus((prev) => ({ ...prev, [item.id]: !open }))}
                    className="flex w-full items-center justify-between px-4 py-3 text-left"
                  >
                    <span className="text-sm font-medium">{item.menu}</span>
                    <span className="text-xs text-muted-foreground">{open ? "접기" : "보기"}</span>
                  </button>
                  <div className={cn("border-t border-border px-4", open ? "block" : "hidden")}>
                    <div className="space-y-2 py-3 text-sm">
                      <p><span className="font-medium">무엇:</span> {item.what}</p>
                      <p><span className="font-medium">어떤 값:</span> {item.values}</p>
                      <p><span className="font-medium">왜:</span> {item.why}</p>
                    </div>
                  </div>
                </article>
              );
            })}
          </div>

          <div id="ops-faq" className="space-y-3">
            <p className="text-lg font-semibold">Ops / FAQ</p>
            <article className="rounded-md border border-border bg-card p-4 text-sm">
              <p className="font-medium">초기 2주 운영 기준</p>
              <p className="mt-2 text-muted-foreground">Day 1-2: Organization baseline / Day 3-5: Team 정책·키 / Day 6-10: 모니터링 튜닝 / Day 11-14: 권한·정책 리뷰</p>
            </article>
            {FAQ_ITEMS.map((item) => (
              <article key={item.q} className="rounded-md border border-border bg-card p-4 text-sm">
                <p className="font-medium">Q. {item.q}</p>
                <p className="mt-1 text-muted-foreground">A. {item.a}</p>
              </article>
            ))}
          </div>

          <div className="rounded-md border border-border bg-card p-4">
            <p className="text-sm font-semibold">바로가기</p>
            <div className="mt-3 flex flex-wrap gap-2">
              <Link href="/dashboard/access/organizations"><Button type="button" variant="outline" className="h-8 px-3 text-xs">Organizations</Button></Link>
              <Link href="/dashboard/access/team-policy"><Button type="button" variant="outline" className="h-8 px-3 text-xs">Team Policy</Button></Link>
              <Link href="/dashboard/security"><Button type="button" variant="outline" className="h-8 px-3 text-xs">Security</Button></Link>
              <Link href="/dashboard/integrations/oauth"><Button type="button" variant="outline" className="h-8 px-3 text-xs">OAuth</Button></Link>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
