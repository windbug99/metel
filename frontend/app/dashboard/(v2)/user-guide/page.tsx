"use client";

import PageTitleWithTooltip from "@/components/dashboard-v2/page-title-with-tooltip";

export default function DashboardUserGuidePage() {
  return (
    <section className="space-y-4">
      <PageTitleWithTooltip
        title="User Guide"
        tooltip="초기 설정과 메뉴별 설정 방법을 안내합니다."
      />
      <article className="ds-card p-4">
        <p className="text-sm text-muted-foreground">
          User Guide 문서는 현재 작성 완료되었습니다.
        </p>
        <p className="mt-2 text-sm text-muted-foreground">
          다음 단계에서 MD 문서를 기반으로 본문 렌더러를 연결할 예정입니다.
        </p>
      </article>
    </section>
  );
}
