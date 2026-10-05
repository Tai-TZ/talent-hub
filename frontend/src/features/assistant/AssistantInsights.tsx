"use client";

import { QueryState } from "@/components/ui/QueryState";
import { Stat } from "@/components/ui/Kit";
import type { components } from "@/lib/api-types";
import { fmtAgo, fmtNumber, fmtPct } from "@/lib/format";
import { useGet } from "@/lib/hooks";

type Insights = components["schemas"]["AssistantInsightsOut"];

/** Cho ban tuyển sinh: những câu hỏi trợ lý không trả lời được chính là danh sách tài liệu cần bổ sung. */
export function AssistantInsights() {
  const query = useGet<Insights>("/admin/assistant/insights?days=30");
  return (
    <section className="th-card panel stack" aria-labelledby="insights-title">
      <h2 id="insights-title" className="th-type-h4">
        Chất lượng trợ lý hỏi đáp (30 ngày)
      </h2>
      <QueryState query={query} lines={2}>
        {(data) =>
          data.total === 0 ? (
            <p className="muted">Chưa có câu hỏi nào. Khi ứng viên bắt đầu hỏi, các câu trợ lý chưa trả lời được sẽ hiện ở đây để bạn biết cần bổ sung tài liệu nào.</p>
          ) : (
            <>
              <div className="stat-grid">
                <Stat label="Câu hỏi" value={fmtNumber(data.total)} />
                <Stat label="Trả lời được" value={fmtPct(data.answer_rate)} tone={(data.answer_rate ?? 0) >= 0.8 ? "ok" : "warn"} hint="Còn lại là câu tài liệu chưa có" />
                <Stat label="Người dùng thấy hữu ích" value={fmtPct(data.helpful_rate)} hint="Trên số câu được đánh giá" />
              </div>
              {data.unanswered.length > 0 ? (
                <>
                  <h3 className="th-type-h5">Câu hỏi chưa trả lời được (bổ sung tài liệu để cải thiện)</h3>
                  <ul className="plain-list stack">
                    {data.unanswered.map((u) => (
                      <li key={u.question} className="row-actions">
                        <span className="score-chip">{u.count}×</span>
                        <span>{u.question}</span>
                        <span className="muted">{fmtAgo(u.last_at)}</span>
                      </li>
                    ))}
                  </ul>
                </>
              ) : null}
            </>
          )
        }
      </QueryState>
    </section>
  );
}
