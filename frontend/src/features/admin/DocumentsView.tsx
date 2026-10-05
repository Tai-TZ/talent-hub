"use client";

import { useRef, useState } from "react";
import { Alert } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { EmptyState } from "@/components/ui/EmptyState";
import { SelectField } from "@/components/ui/Fields";
import { PageHeader, Pager } from "@/components/ui/Kit";
import { QueryState } from "@/components/ui/QueryState";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { TextField } from "@/components/ui/TextField";
import type { DocumentDetail, DocumentPage, SearchHit } from "@/lib/contracts";
import { fmtDateTime, fmtNumber } from "@/lib/format";
import { errorText, useGet, useSend } from "@/lib/hooks";
import { docStatus } from "@/lib/labels";
import { AssistantInsights } from "@/features/assistant/AssistantInsights";

const LIMIT = 25;
const MAX_FILE = 15 * 1024 * 1024;
const ACCEPT = ".txt,.md,.markdown,.csv,.pdf,.docx";

/** Đọc tệp thành base64 (không dùng btoa trên chuỗi lớn để tránh tràn bộ nhớ ngăn xếp). */
function toBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).split(",", 2)[1] ?? "");
    reader.onerror = () => reject(new Error("Không đọc được tệp"));
    reader.readAsDataURL(file);
  });
}

function UploadForm({ onClose }: { onClose: () => void }) {
  const input = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [visibility, setVisibility] = useState("public");
  const [error, setError] = useState<string | null>(null);
  const [reading, setReading] = useState(false);
  const upload = useSend<unknown, { title: string; visibility: string; filename: string; content_base64: string }>("POST", "/admin/documents", { invalidate: ["/admin/documents", "/admin/overview"] });

  function pick(f: File | null) {
    setError(null);
    if (f && f.size > MAX_FILE) {
      setError("Tệp quá lớn (tối đa 15 MB).");
      setFile(null);
      return;
    }
    setFile(f);
    if (f && !title) setTitle(f.name.replace(/\.[^.]+$/, ""));
  }

  async function submit() {
    if (!file) return;
    setError(null);
    setReading(true);
    try {
      const content_base64 = await toBase64(file);
      upload.mutate({ title: title.trim(), visibility, filename: file.name, content_base64 }, { onSuccess: onClose, onError: (e) => setError(errorText(e)) });
    } catch (e) {
      setError(errorText(e));
    } finally {
      setReading(false);
    }
  }

  return (
    <form
      className="stack"
      onSubmit={(e) => {
        e.preventDefault();
        void submit();
      }}
    >
      <div className="th-field">
        <label className="th-field__label" htmlFor="doc-file">
          Tệp tài liệu <span className="th-field__required" aria-hidden="true">*</span>
        </label>
        <input id="doc-file" ref={input} className="th-input" type="file" accept={ACCEPT} onChange={(e) => pick(e.target.files?.[0] ?? null)} />
        <span className="th-field__help">PDF, Word (.docx), văn bản (.txt, .md, .csv); tối đa 15 MB. Văn bản được trích và chia đoạn để tìm kiếm.</span>
      </div>
      <TextField label="Tiêu đề" required value={title} maxLength={200} onChange={(e) => setTitle(e.target.value)} />
      <SelectField label="Phạm vi" value={visibility} onChange={(e) => setVisibility(e.target.value)} help="Công khai: trợ lý trả lời được cho mọi người. Nội bộ: chỉ nhân sự.">
        <option value="public">Công khai (ứng viên cũng thấy)</option>
        <option value="internal">Nội bộ (chỉ nhân sự)</option>
      </SelectField>
      <Alert tone="info">Không tải lên tài liệu chứa thông tin cá nhân của ứng viên. Tệp được kiểm tra loại và kích thước, trùng nội dung sẽ bị từ chối.</Alert>
      {error ? <Alert tone="danger">{error}</Alert> : null}
      <div className="dialog__actions">
        <Button variant="secondary" onClick={onClose}>
          Huỷ
        </Button>
        <Button type="submit" loading={reading || upload.isPending} disabled={!file || !title.trim()}>
          Tải lên
        </Button>
      </div>
    </form>
  );
}

function Detail({ id }: { id: string }) {
  const query = useGet<DocumentDetail>(`/admin/documents/${id}`);
  return (
    <QueryState query={query} lines={4}>
      {(d) => (
        <div className="stack">
          <dl className="summary">
            <div><dt>Tệp</dt><dd>{d.filename}</dd></div>
            <div><dt>Kích thước</dt><dd>{fmtNumber(Math.round(d.size_bytes / 1024))} KB · {fmtNumber(d.char_count)} ký tự · {d.chunk_count} đoạn</dd></div>
            <div><dt>Phạm vi</dt><dd>{d.visibility === "public" ? "Công khai" : "Nội bộ"}</dd></div>
            <div><dt>Tải lên</dt><dd>{fmtDateTime(d.created_at)}</dd></div>
          </dl>
          <h3 className="th-type-h5">Xem trước các đoạn đầu</h3>
          <ul className="plain-list stack">
            {d.preview.map((c) => (
              <li key={c.ordinal} className="ai-criterion">
                {c.heading ? <strong>{c.heading}</strong> : null}
                <p className="record-text">{c.content}</p>
              </li>
            ))}
          </ul>
        </div>
      )}
    </QueryState>
  );
}

function SearchTester() {
  const [q, setQ] = useState("");
  const [term, setTerm] = useState("");
  const hits = useGet<SearchHit[]>(term ? `/admin/documents-search?q=${encodeURIComponent(term)}` : null);
  return (
    <section className="th-card panel stack" aria-labelledby="search-title">
      <h2 id="search-title" className="th-type-h4">
        Thử tìm kiếm
      </h2>
      <p className="muted">Kiểm tra tài liệu đã được lập chỉ mục đúng chưa, như cách trợ lý sẽ tìm (không phân biệt dấu tiếng Việt).</p>
      <form
        className="toolbar"
        onSubmit={(e) => {
          e.preventDefault();
          setTerm(q.trim());
        }}
      >
        <TextField label="Câu hỏi hoặc từ khoá" value={q} onChange={(e) => setQ(e.target.value)} placeholder="điều kiện dự tuyển" />
        <Button type="submit" variant="secondary" disabled={!q.trim()}>
          Tìm
        </Button>
      </form>
      {term ? (
        <QueryState query={hits} lines={3}>
          {(list) =>
            list.length === 0 ? (
              <p className="muted">Không tìm thấy đoạn nào phù hợp.</p>
            ) : (
              <ul className="plain-list stack">
                {list.map((h) => (
                  <li key={h.chunk_id} className="ai-criterion">
                    <div className="row-actions">
                      <strong>{h.title}</strong>
                      {h.heading ? <span className="muted">· {h.heading}</span> : null}
                      <StatusBadge entry={h.visibility === "public" ? ["Công khai", "success"] : ["Nội bộ", "warning"]} />
                      <span className="muted">điểm {h.score}</span>
                    </div>
                    <p className="record-text">{h.snippet}</p>
                  </li>
                ))}
              </ul>
            )
          }
        </QueryState>
      ) : null}
    </section>
  );
}

export function DocumentsView() {
  const [status, setStatus] = useState("");
  const [offset, setOffset] = useState(0);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [detail, setDetail] = useState<string | null>(null);
  const [message, setMessage] = useState<{ tone: "success" | "danger"; text: string } | null>(null);
  const params = new URLSearchParams({ limit: String(LIMIT), offset: String(offset) });
  if (status) params.set("status", status);
  const list = useGet<DocumentPage>(`/admin/documents?${params}`);
  const retire = useSend<unknown, { id: string }>("POST", (v) => `/admin/documents/${v.id}/retire`, { invalidate: ["/admin/documents", "/admin/overview"] });
  const restore = useSend<unknown, { id: string }>("POST", (v) => `/admin/documents/${v.id}/restore`, { invalidate: ["/admin/documents", "/admin/overview"] });

  return (
    <div className="stack">
      <PageHeader title="Tài liệu" subtitle="Kho tri thức cho trợ lý hỏi đáp và ban tuyển sinh: quy chế, thông báo, câu hỏi thường gặp." actions={<Button onClick={() => setUploadOpen(true)}>Tải tài liệu lên</Button>} />
      <div className="toolbar">
        <SelectField
          label="Trạng thái"
          value={status}
          onChange={(e) => {
            setStatus(e.target.value);
            setOffset(0);
          }}
        >
          <option value="">Tất cả</option>
          <option value="ready">Sẵn sàng</option>
          <option value="retired">Đã gỡ</option>
          <option value="failed">Lỗi xử lý</option>
        </SelectField>
      </div>
      {message ? <Alert tone={message.tone}>{message.text}</Alert> : null}
      <QueryState query={list} lines={5}>
        {(page) =>
          page.items.length === 0 ? (
            <EmptyState title="Chưa có tài liệu nào">Tải lên quy chế tuyển sinh hoặc câu hỏi thường gặp để trợ lý có nguồn trả lời.</EmptyState>
          ) : (
            <>
              <div className="table-wrap">
                <table className="th-table responsive-table">
                  <thead>
                    <tr>
                      <th scope="col">Tài liệu</th>
                      <th scope="col">Phạm vi</th>
                      <th scope="col">Trạng thái</th>
                      <th scope="col">Đoạn</th>
                      <th scope="col">Tải lên</th>
                      <th scope="col">Thao tác</th>
                    </tr>
                  </thead>
                  <tbody>
                    {page.items.map((d) => (
                      <tr key={d.id}>
                        <td data-label="Tài liệu">
                          <button type="button" className="link-button" onClick={() => setDetail(d.id)}>
                            {d.title}
                          </button>
                          <div className="muted">{d.filename}</div>
                        </td>
                        <td data-label="Phạm vi">{d.visibility === "public" ? "Công khai" : "Nội bộ"}</td>
                        <td data-label="Trạng thái">
                          <StatusBadge entry={docStatus(d.status)} />
                        </td>
                        <td data-label="Đoạn">{fmtNumber(d.chunk_count)}</td>
                        <td data-label="Tải lên">{fmtDateTime(d.created_at)}</td>
                        <td data-label="Thao tác">
                          {d.status === "ready" ? (
                            <Button
                              variant="tertiary"
                              size="sm"
                              loading={retire.isPending && retire.variables?.id === d.id}
                              onClick={() => retire.mutate({ id: d.id }, { onSuccess: () => setMessage({ tone: "success", text: `Đã gỡ "${d.title}" khỏi kết quả tìm kiếm.` }), onError: (e) => setMessage({ tone: "danger", text: errorText(e) }) })}
                            >
                              Gỡ
                            </Button>
                          ) : d.status === "retired" ? (
                            <Button
                              variant="tertiary"
                              size="sm"
                              loading={restore.isPending && restore.variables?.id === d.id}
                              onClick={() => restore.mutate({ id: d.id }, { onSuccess: () => setMessage({ tone: "success", text: `Đã khôi phục "${d.title}".` }), onError: (e) => setMessage({ tone: "danger", text: errorText(e) }) })}
                            >
                              Khôi phục
                            </Button>
                          ) : null}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <Pager total={page.total} offset={offset} limit={LIMIT} onChange={setOffset} label="Phân trang tài liệu" />
            </>
          )
        }
      </QueryState>

      <AssistantInsights />

      <SearchTester />

      <Dialog open={uploadOpen} title="Tải tài liệu lên" size="md" onClose={() => setUploadOpen(false)}>
        <UploadForm onClose={() => setUploadOpen(false)} />
      </Dialog>
      <Dialog open={detail !== null} title="Chi tiết tài liệu" size="lg" onClose={() => setDetail(null)}>
        {detail ? <Detail id={detail} /> : null}
      </Dialog>
    </div>
  );
}
