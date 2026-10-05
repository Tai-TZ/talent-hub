"use client";

import { Alert } from "@/components/ui/Alert";
import { SelectField } from "@/components/ui/Fields";
import { DemoNotice, PageHeader, Tabs } from "@/components/ui/Kit";
import { QueryState } from "@/components/ui/QueryState";
import { useCohortSelection } from "@/lib/use-cohort-selection";
import { ComposerTab } from "./ComposerTab";
import { EnrollmentsTab } from "./EnrollmentsTab";
import { OverviewTab } from "./OverviewTab";
import { QualificationTab } from "./QualificationTab";
import { StipendsTab } from "./StipendsTab";

export function CohortsView() {
  const { query, cohorts, selected, select } = useCohortSelection();
  return (
    <div className="stack">
      <PageHeader title="Khoá học" subtitle="Ghi danh, xếp lớp và nhánh, theo dõi năng lực, xét đạt và phụ cấp của từng khoá." />
      <QueryState query={query} lines={2}>
        {() =>
          !selected ? (
            <Alert tone="info">Chưa có khoá học nào. Quản trị viên tạo chương trình và khoá trong phần Đợt tuyển.</Alert>
          ) : (
            <>
              <div className="toolbar">
                <SelectField label="Khoá học" value={selected.id} onChange={(e) => select(e.target.value)}>
                  {cohorts.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name} ({c.code})
                    </option>
                  ))}
                </SelectField>
              </div>
              <DemoNotice show={selected.name.startsWith("[Minh hoạ]")} />
              <Tabs
                key={selected.id}
                items={[
                  { id: "overview", label: "Tổng quan", content: <OverviewTab cohortId={selected.id} /> },
                  { id: "learners", label: "Học viên", content: <EnrollmentsTab cohortId={selected.id} /> },
                  { id: "composer", label: "Cohort Composer", content: <ComposerTab cohortId={selected.id} /> },
                  { id: "qualification", label: "Xét đạt", content: <QualificationTab cohortId={selected.id} /> },
                  { id: "stipends", label: "Phụ cấp", content: <StipendsTab cohortId={selected.id} /> },
                ]}
              />
            </>
          )
        }
      </QueryState>
    </div>
  );
}
