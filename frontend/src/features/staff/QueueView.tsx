"use client";

import { useInfiniteQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useDeferredValue, useState } from "react";
import { IntakePicker } from "@/components/IntakePicker";
import { useMe } from "@/components/providers";
import { Alert } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { Checkbox, SelectField } from "@/components/ui/Fields";
import { DemoNotice, PageHeader, Stat } from "@/components/ui/Kit";
import { QueryState } from "@/components/ui/QueryState";
import { Skeleton } from "@/components/ui/Skeleton";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { TextField } from "@/components/ui/TextField";
import { api } from "@/lib/api";
import type { QueuePage } from "@/lib/contracts";
import { fmtDateTime, fmtNumber, fmtScore } from "@/lib/format";
import { errorText, useSend } from "@/lib/hooks";
import { applicationStatus, tierLabel } from "@/lib/labels";
import { useIntakeSelection } from "@/lib/use-intake-selection";

const STATUS_OPTIONS = ["SUBMITTED", "IN_ROUND", "NEEDS_INFO", "PENDING_APPROVAL", "ACCEPTED", "WAITLISTED", "REJECTED", "ENROLLED", "WITHDRAWN"];
const PAGE_SIZE = 50;

export function QueueView() {
  const me = useMe();
  const { query: intakesQuery, intakes, selected, select } = useIntakeSelection();
  const [status, setStatus] = useState("");
  const [round, setRound] = useState("");
  const [search, setSearch] = useState("");
  const [minePending, setMinePending] = useState(false);
  const [attention, setAttention] = useState(false);
  const q = useDeferredValue(search.trim());
  const canStart = me.permissions.includes("application.assign");
  const intakeId = selected?.id;

  const queue = useInfiniteQuery({
    queryKey: ["api", "/staff/applications", intakeId, status, round, q, minePending, attention],
    enabled: Boolean(intakeId),
    initialPageParam: null as string | null,
    queryFn: ({ pageParam }) => {
      const params = new URLSearchParams({ intake_id: intakeId as string, limit: String(PAGE_SIZE) });
      if (status) params.set("status", status);
      if (round) params.set("round", round);
      if (q) params.set("q", q);
      if (minePending) params.set("mine_pending", "true");
      if (attention) params.set("needs_attention", "true");
      if (pageParam) params.set("cursor", pageParam);
      return api<QueuePage>(`/staff/applications?${params}`);
    },
    getNextPageParam: (last) => last.next_cursor,
  });

  const start = useSend<{ moved: number }>("POST", `/intakes/${intakeId}/start`, { invalidate: ["/staff/applications", "/intakes"] });
  const [startMessage, setStartMessage] = useState<string | null>(null);

  const items = queue.data?.pages.flatMap((p) => p.items) ?? [];
  const first = queue.data?.pages[0];
  const showTier = items.some((i) => i.ai_tier !== undefined && i.ai_tier !== null);
  const counts = selected?.counts ?? {};
  const waiting = counts["SUBMITTED"] ?? 0;

  return (
    <div className="stack">
      <PageHeader title="Hàng đợi hồ sơ" subtitle="Lọc, tìm kiếm và mở hồ sơ để chấm. Mọi thao tác đều được ghi nhật ký." />

      <QueryState query={intakesQuery} lines={2}>
        {() => (
          <>
            <div className="toolbar">
              <IntakePicker
                intakes={intakes}
                selected={selected}
                onSelect={(id) => {
                  setRound(""); // khoá vòng thuộc cấu hình từng đợt: giữ lại sẽ lọc theo một vòng không tồn tại
                  select(id);
                }}
              />
              <SelectField label="Trạng thái" value={status} onChange={(e) => setStatus(e.target.value)}>
                <option value="">Tất cả</option>
                {STATUS_OPTIONS.map((s) => (
                  <option key={s} value={s}>
                    {applicationStatus(s)[0]}
                  </option>
                ))}
              </SelectField>
              <SelectField label="Vòng" value={round} onChange={(e) => setRound(e.target.value)}>
                <option value="">Tất cả</option>
                {selected?.rounds.map((r) => (
                  <option key={r.key} value={r.key}>
                    {r.label}
                  </option>
                ))}
              </SelectField>
              <TextField label="Tìm theo mã hồ sơ" type="search" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="A-1B2C3D…" />
            </div>
            <div className="row-actions">
              <Checkbox label="Chỉ hồ sơ tôi chưa chấm" checked={minePending} onChange={(e) => setMinePending(e.target.checked)} />
              <Checkbox label="Chỉ hồ sơ AI đánh dấu ưu tiên xem kỹ" checked={attention} onChange={(e) => setAttention(e.target.checked)} />
            </div>

            <DemoNotice show={Boolean(selected?.name.startsWith("[Minh hoạ]"))} />

            {selected ? (
              <div className="stat-grid">
                <Stat label="Chờ vào vòng" value={fmtNumber(waiting)} tone={waiting > 0 ? "warn" : undefined} />
                <Stat label="Đang xét" value={fmtNumber(counts["IN_ROUND"] ?? 0)} />
                <Stat label="Chờ phê duyệt" value={fmtNumber(counts["PENDING_APPROVAL"] ?? 0)} />
                <Stat label="Được nhận" value={fmtNumber((counts["ACCEPTED"] ?? 0) + (counts["ENROLLED"] ?? 0))} hint={`Chỉ tiêu ${fmtNumber(selected.quota)}`} tone="ok" />
              </div>
            ) : null}

            {canStart && waiting > 0 && selected?.status === "closed" ? (
              <Alert tone="info" title={`${fmtNumber(waiting)} hồ sơ đang chờ vào vòng đầu`}>
                Đợt tuyển đã đóng. Chuyển toàn bộ hồ sơ đã nộp vào vòng đầu để bắt đầu chấm.
                <div style={{ marginTop: "var(--th-space-3)" }}>
                  <Button
                    size="sm"
                    loading={start.isPending}
                    onClick={() => {
                      setStartMessage(null);
                      start.mutate(undefined, {
                        onSuccess: (r) => setStartMessage(`Đã chuyển ${fmtNumber(r.moved)} hồ sơ vào vòng đầu.`),
                        onError: (e) => setStartMessage(errorText(e)),
                      });
                    }}
                  >
                    Bắt đầu vòng đầu
                  </Button>
                </div>
              </Alert>
            ) : null}
            {startMessage ? <Alert tone="info">{startMessage}</Alert> : null}

            {first?.blind_review ? <p className="muted">Đợt này chấm mù: họ tên và liên kết cá nhân được ẩn với người không có quyền xem danh tính.</p> : null}

            {queue.isPending && intakeId ? (
              <Skeleton lines={6} />
            ) : queue.isError ? (
              <Alert tone="danger">
                {errorText(queue.error)}{" "}
                <Button variant="tertiary" size="sm" onClick={() => void queue.refetch()}>
                  Thử lại
                </Button>
              </Alert>
            ) : items.length === 0 ? (
              <EmptyState title="Không có hồ sơ phù hợp bộ lọc" />
            ) : (
              <>
                <p className="muted" aria-live="polite">
                  Hiển thị {fmtNumber(items.length)} / {fmtNumber(first?.total ?? 0)} hồ sơ
                </p>
                <div className="table-wrap">
                  <table className="th-table responsive-table">
                    <thead>
                      <tr>
                        <th scope="col">Mã hồ sơ</th>
                        <th scope="col">Họ tên</th>
                        <th scope="col">Trạng thái</th>
                        <th scope="col">Vòng</th>
                        <th scope="col">Đã chấm</th>
                        <th scope="col">Của tôi</th>
                        <th scope="col">{showTier ? "Gợi ý AI" : "AI"}</th>
                        <th scope="col">Cờ</th>
                        <th scope="col">Nộp lúc</th>
                      </tr>
                    </thead>
                    <tbody>
                      {items.map((item) => (
                        <tr key={item.id}>
                          <td data-label="Mã hồ sơ">
                            <Link href={`/staff/applications/${item.id}`} className="mono">
                              {item.candidate_code}
                            </Link>
                          </td>
                          <td data-label="Họ tên">{item.name ?? <span className="muted">Ẩn danh</span>}</td>
                          <td data-label="Trạng thái">
                            <StatusBadge entry={applicationStatus(item.status)} />
                          </td>
                          <td data-label="Vòng">{selected?.rounds.find((r) => r.key === item.current_round)?.label ?? "—"}</td>
                          <td data-label="Đã chấm">{item.review_count}</td>
                          <td data-label="Của tôi">{item.my_review === "submitted" ? "Đã chốt" : item.my_review === "draft" ? "Nháp" : "—"}</td>
                          <td data-label="AI">
                            {item.ai_tier ? (
                              <span className="row-actions">
                                <StatusBadge entry={tierLabel(item.ai_tier)} />
                                <span className="score-chip">{fmtScore(item.ai_score)}</span>
                              </span>
                            ) : item.ai_attention ? (
                              <StatusBadge entry={["Ưu tiên xem kỹ", "warning"]} />
                            ) : (
                              "—"
                            )}
                          </td>
                          <td data-label="Cờ">{item.flag_count > 0 ? item.flag_count : "—"}</td>
                          <td data-label="Nộp lúc">{fmtDateTime(item.submitted_at)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {queue.hasNextPage ? (
                  <div className="table-footer">
                    <Button variant="secondary" onClick={() => void queue.fetchNextPage()} loading={queue.isFetchingNextPage}>
                      Tải thêm
                    </Button>
                  </div>
                ) : null}
              </>
            )}
          </>
        )}
      </QueryState>
    </div>
  );
}
