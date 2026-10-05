"use client";

import { useInfiniteQuery } from "@tanstack/react-query";
import { useDeferredValue, useState } from "react";
import { Alert } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { EmptyState } from "@/components/ui/EmptyState";
import { Checkbox, SelectField, TextArea } from "@/components/ui/Fields";
import { PageHeader } from "@/components/ui/Kit";
import { Skeleton } from "@/components/ui/Skeleton";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { TextField } from "@/components/ui/TextField";
import { api } from "@/lib/api";
import type { Account, AccountCreated, AccountPage, ImportResult } from "@/lib/contracts";
import { fmtAgo, fmtNumber } from "@/lib/format";
import { errorText, useSend } from "@/lib/hooks";
import { accountStatus, ROLE_LABELS } from "@/lib/labels";
import { parseAccountsCsv } from "./csv";

const PAGE = 25;
const REFRESH = ["/admin/users", "/admin/overview"];

function InviteLink({ link }: { link: string | null | undefined }) {
  const [copied, setCopied] = useState(false);
  if (!link) return <p className="muted">Lời mời đã được gửi qua email.</p>;
  return (
    <Alert tone="info" title="Link lời mời (chỉ hiện ở môi trường thử nghiệm)">
      <code className="mono" style={{ overflowWrap: "anywhere" }}>
        {link}
      </code>{" "}
      <button
        type="button"
        className="link-button"
        onClick={() => {
          void navigator.clipboard.writeText(link).then(() => setCopied(true));
        }}
      >
        {copied ? "Đã chép" : "Chép link"}
      </button>
    </Alert>
  );
}

function RolePicker({ roles, value, onChange }: { roles: string[]; value: string[]; onChange: (next: string[]) => void }) {
  return (
    <fieldset className="plain-fieldset stack">
      <legend className="th-field__label">Vai trò</legend>
      {roles.map((r) => (
        <Checkbox key={r} label={ROLE_LABELS[r] ?? r} checked={value.includes(r)} onChange={(e) => onChange(e.target.checked ? [...value, r] : value.filter((x) => x !== r))} />
      ))}
    </fieldset>
  );
}

function InviteForm({ roles, onClose }: { roles: string[]; onClose: () => void }) {
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [picked, setPicked] = useState<string[]>([]);
  const [error, setError] = useState<{ message: string; fields: Record<string, string> } | null>(null);
  const create = useSend<AccountCreated, { email: string; full_name: string; roles: string[] }>("POST", "/admin/users", { invalidate: REFRESH });

  if (create.data) {
    return (
      <div className="stack">
        <Alert tone="success">
          Đã tạo tài khoản <strong>{create.data.email}</strong> ({create.data.roles.map((r) => ROLE_LABELS[r] ?? r).join(", ")}).
        </Alert>
        <InviteLink link={create.data.invite_link} />
        <div className="dialog__actions">
          <Button onClick={onClose}>Xong</Button>
        </div>
      </div>
    );
  }

  return (
    <form
      className="stack"
      onSubmit={(e) => {
        e.preventDefault();
        setError(null);
        create.mutate({ email, full_name: name, roles: picked }, { onError: (err) => setError({ message: errorText(err), fields: err.fields }) });
      }}
    >
      <TextField label="Email" type="email" required value={email} autoComplete="off" error={error?.fields["email"]} onChange={(e) => setEmail(e.target.value)} />
      <TextField label="Họ và tên" required value={name} error={error?.fields["full_name"]} onChange={(e) => setName(e.target.value)} />
      <RolePicker roles={roles} value={picked} onChange={setPicked} />
      <p className="muted">Người dùng nhận email có link đặt mật khẩu (hết hạn sau thời gian cấu hình). Admin không bao giờ biết mật khẩu của họ.</p>
      {error ? <Alert tone="danger">{error.message}</Alert> : null}
      <div className="dialog__actions">
        <Button variant="secondary" onClick={onClose}>
          Huỷ
        </Button>
        <Button type="submit" loading={create.isPending} disabled={!email || !name.trim() || picked.length === 0}>
          Gửi lời mời
        </Button>
      </div>
    </form>
  );
}

const IMPORT_HINT = "email,họ tên,vai trò\nan.nguyen@northwind.example.edu,Nguyễn Văn An,reviewer\nbinh.tran@northwind.example.edu,Trần Thị Bình,mentor;reviewer";

function ImportForm({ onClose }: { onClose: () => void }) {
  const [text, setText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const parsed = parseAccountsCsv(text);
  const run = useSend<ImportResult, { rows: typeof parsed.rows; dry_run: boolean }>("POST", "/admin/users/import", { invalidate: REFRESH });
  const result = run.data;
  const created = result && !result.dry_run;

  function submit(dry: boolean) {
    setError(null);
    run.mutate({ rows: parsed.rows, dry_run: dry }, { onError: (e) => setError(errorText(e)) });
  }

  return (
    <div className="stack">
      {created ? null : (
        <>
          <TextArea label="Danh sách tài khoản (dán từ Excel hoặc CSV)" rows={6} value={text} placeholder={IMPORT_HINT} onChange={(e) => setText(e.target.value)} help="Mỗi dòng: email, họ tên, vai trò (nhiều vai trò cách nhau bằng dấu ;). Tối đa 1.000 dòng." />
          {parsed.problems.length > 0 ? (
            <Alert tone="warning" title="Có dòng không đọc được">
              <ul className="plain-list">
                {parsed.problems.slice(0, 5).map((p) => (
                  <li key={p.line}>
                    Dòng {p.line}: {p.message}
                  </li>
                ))}
              </ul>
            </Alert>
          ) : null}
        </>
      )}

      {result ? (
        <>
          <Alert tone={result.summary.error > 0 ? "warning" : "success"}>
            {result.dry_run ? "Kiểm tra thử (chưa tạo tài khoản): " : "Đã tạo: "}
            {result.dry_run ? `${result.summary.ok} hợp lệ` : `${result.summary.created} tài khoản`}, {result.summary.error} lỗi.
          </Alert>
          <div className="table-wrap table-wrap--scroll" style={{ maxHeight: 280, overflow: "auto" }}>
            <table className="th-table">
              <thead>
                <tr>
                  <th scope="col">Dòng</th>
                  <th scope="col">Email</th>
                  <th scope="col">Kết quả</th>
                </tr>
              </thead>
              <tbody>
                {result.rows.map((r) => (
                  <tr key={r.row}>
                    <td>{r.row}</td>
                    <td>{r.email}</td>
                    <td>
                      <StatusBadge entry={r.status === "error" ? [r.error ?? "Lỗi", "danger"] : r.status === "created" ? ["Đã tạo", "success"] : ["Hợp lệ", "success"]} />
                      {r.invite_link ? (
                        <div className="mono muted" style={{ overflowWrap: "anywhere" }}>
                          {r.invite_link}
                        </div>
                      ) : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      ) : null}

      {error ? <Alert tone="danger">{error}</Alert> : null}
      <div className="dialog__actions">
        <Button variant="secondary" onClick={onClose}>
          {created ? "Đóng" : "Huỷ"}
        </Button>
        {created ? null : (
          <>
            <Button variant="secondary" loading={run.isPending && run.variables?.dry_run} disabled={parsed.rows.length === 0} onClick={() => submit(true)}>
              Kiểm tra trước
            </Button>
            <Button loading={run.isPending && !run.variables?.dry_run} disabled={parsed.rows.length === 0 || !result?.dry_run || result.summary.ok === 0} onClick={() => submit(false)}>
              Tạo {result?.dry_run ? result.summary.ok : parsed.rows.length} tài khoản
            </Button>
          </>
        )}
      </div>
    </div>
  );
}

function EditForm({ account, roles, onClose }: { account: Account; roles: string[]; onClose: () => void }) {
  const [picked, setPicked] = useState(account.roles);
  const [status, setStatus] = useState(account.status === "suspended" ? "suspended" : "active");
  const [error, setError] = useState<string | null>(null);
  const save = useSend<unknown, { roles: string[]; status?: string }>("PATCH", `/admin/users/${account.membership_id}`, { invalidate: REFRESH });
  return (
    <form
      className="stack"
      onSubmit={(e) => {
        e.preventDefault();
        save.mutate({ roles: picked, status: account.status === "invited" ? undefined : status }, { onSuccess: onClose, onError: (err) => setError(errorText(err)) });
      }}
    >
      <p>
        <strong>{account.full_name}</strong> · {account.email}
      </p>
      <RolePicker roles={roles} value={picked} onChange={setPicked} />
      {account.status !== "invited" ? (
        <SelectField label="Trạng thái" value={status} onChange={(e) => setStatus(e.target.value)} help="Khoá tài khoản sẽ thu hồi mọi phiên đăng nhập ngay lập tức.">
          <option value="active">Hoạt động</option>
          <option value="suspended">Khoá</option>
        </SelectField>
      ) : null}
      {error ? <Alert tone="danger">{error}</Alert> : null}
      <div className="dialog__actions">
        <Button variant="secondary" onClick={onClose}>
          Huỷ
        </Button>
        <Button type="submit" loading={save.isPending} disabled={picked.length === 0}>
          Lưu thay đổi
        </Button>
      </div>
    </form>
  );
}

type Modal = { kind: "invite" } | { kind: "import" } | { kind: "edit"; account: Account } | null;

export function UsersView() {
  const [search, setSearch] = useState("");
  const [role, setRole] = useState("");
  const [status, setStatus] = useState("");
  const [audience, setAudience] = useState<"staff" | "applicant" | "">("staff");
  const [modal, setModal] = useState<Modal>(null);
  const [notice, setNotice] = useState<{ tone: "success" | "danger" | "info"; text: string; link?: string | null } | null>(null);
  const q = useDeferredValue(search.trim());

  const list = useInfiniteQuery({
    queryKey: ["api", "/admin/users", q, role, status, audience],
    initialPageParam: null as string | null,
    queryFn: ({ pageParam }) => {
      const params = new URLSearchParams({ limit: String(PAGE) });
      if (q) params.set("q", q);
      if (role) params.set("role", role);
      if (status) params.set("status", status);
      if (audience) params.set("audience", audience);
      if (pageParam) params.set("cursor", pageParam);
      return api<AccountPage>(`/admin/users?${params}`);
    },
    getNextPageParam: (last) => last.next_cursor,
  });

  const resend = useSend<{ invite_link: string | null }, { id: string }>("POST", (v) => `/admin/users/${v.id}/invite`, { invalidate: REFRESH });
  const reset = useSend<unknown, { id: string }>("POST", (v) => `/admin/users/${v.id}/reset-password`);

  const items = list.data?.pages.flatMap((p) => p.items) ?? [];
  const first = list.data?.pages[0];
  const roles = first?.assignable_roles ?? [];

  return (
    <div className="stack">
      <PageHeader
        title="Tài khoản"
        subtitle="Cấp, phân quyền và khoá tài khoản. Nhân sự được mời qua email hoặc đăng nhập bằng tài khoản Microsoft đã được liên kết."
        actions={
          <>
            <Button variant="secondary" onClick={() => setModal({ kind: "import" })}>
              Nhập hàng loạt
            </Button>
            <Button onClick={() => setModal({ kind: "invite" })}>Mời người dùng</Button>
          </>
        }
      />

      <div className="row-actions" role="group" aria-label="Nhóm người dùng">
        {(
          [
            ["staff", "Nhân sự"],
            ["applicant", "Ứng viên"],
            ["", "Tất cả"],
          ] as const
        ).map(([value, label]) => (
          <button key={value} type="button" className="chip" aria-pressed={audience === value} onClick={() => setAudience(value)}>
            {label}
          </button>
        ))}
      </div>

      <div className="toolbar">
        <TextField label="Tìm theo tên hoặc email" type="search" value={search} onChange={(e) => setSearch(e.target.value)} />
        <SelectField label="Vai trò" value={role} onChange={(e) => setRole(e.target.value)}>
          <option value="">Tất cả</option>
          {roles.map((r) => (
            <option key={r} value={r}>
              {ROLE_LABELS[r] ?? r}
            </option>
          ))}
        </SelectField>
        <SelectField label="Trạng thái" value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="">Tất cả</option>
          <option value="active">Hoạt động</option>
          <option value="invited">Đã mời</option>
          <option value="suspended">Bị khoá</option>
        </SelectField>
      </div>

      {notice ? (
        <Alert tone={notice.tone}>
          {notice.text}
          {notice.link ? <InviteLink link={notice.link} /> : null}
        </Alert>
      ) : null}

      {list.isPending ? (
        <Skeleton lines={6} />
      ) : list.isError ? (
        <Alert tone="danger">{errorText(list.error)}</Alert>
      ) : items.length === 0 ? (
        <EmptyState title="Không có tài khoản phù hợp" />
      ) : (
        <>
          <p className="muted" aria-live="polite">
            {fmtNumber(items.length)} / {fmtNumber(first?.total ?? 0)} tài khoản
          </p>
          <div className="table-wrap">
            <table className="th-table responsive-table">
              <thead>
                <tr>
                  <th scope="col">Người dùng</th>
                  <th scope="col">Vai trò</th>
                  <th scope="col">Trạng thái</th>
                  <th scope="col">Đăng nhập gần nhất</th>
                  <th scope="col">Thao tác</th>
                </tr>
              </thead>
              <tbody>
                {items.map((a) => (
                  <tr key={a.membership_id}>
                    <td data-label="Người dùng">
                      {a.full_name}
                      <div className="muted">{a.email}</div>
                    </td>
                    <td data-label="Vai trò">{a.roles.map((r) => ROLE_LABELS[r] ?? r).join(", ") || "—"}</td>
                    <td data-label="Trạng thái">
                      <span className="row-actions">
                        <StatusBadge entry={accountStatus(a.status)} />
                        {a.locked ? <StatusBadge entry={["Khoá tạm", "warning"]} /> : null}
                      </span>
                    </td>
                    <td data-label="Đăng nhập gần nhất">{a.last_login_at ? fmtAgo(a.last_login_at) : "Chưa bao giờ"}</td>
                    <td data-label="Thao tác">
                      <span className="row-actions">
                        <Button variant="tertiary" size="sm" onClick={() => setModal({ kind: "edit", account: a })}>
                          Sửa
                        </Button>
                        {a.status === "invited" ? (
                          <Button
                            variant="tertiary"
                            size="sm"
                            loading={resend.isPending && resend.variables?.id === a.membership_id}
                            onClick={() => {
                              setNotice(null);
                              resend.mutate({ id: a.membership_id }, { onSuccess: (r) => setNotice({ tone: "success", text: `Đã gửi lại lời mời cho ${a.email}.`, link: r.invite_link }), onError: (e) => setNotice({ tone: "danger", text: errorText(e) }) });
                            }}
                          >
                            Gửi lại lời mời
                          </Button>
                        ) : (
                          <Button
                            variant="tertiary"
                            size="sm"
                            loading={reset.isPending && reset.variables?.id === a.membership_id}
                            onClick={() => {
                              setNotice(null);
                              reset.mutate({ id: a.membership_id }, { onSuccess: () => setNotice({ tone: "success", text: `Đã gửi link đặt lại mật khẩu tới email của ${a.email}. Admin không nhận được link này.` }), onError: (e) => setNotice({ tone: "danger", text: errorText(e) }) });
                            }}
                          >
                            Đặt lại mật khẩu
                          </Button>
                        )}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {list.hasNextPage ? (
            <div className="table-footer">
              <Button variant="secondary" onClick={() => void list.fetchNextPage()} loading={list.isFetchingNextPage}>
                Tải thêm
              </Button>
            </div>
          ) : null}
        </>
      )}

      <Dialog open={modal?.kind === "invite"} title="Mời người dùng" size="md" onClose={() => setModal(null)}>
        <InviteForm roles={roles} onClose={() => setModal(null)} />
      </Dialog>
      <Dialog open={modal?.kind === "import"} title="Nhập tài khoản hàng loạt" size="lg" onClose={() => setModal(null)}>
        <ImportForm onClose={() => setModal(null)} />
      </Dialog>
      <Dialog open={modal?.kind === "edit"} title="Sửa tài khoản" size="md" onClose={() => setModal(null)}>
        {modal?.kind === "edit" ? <EditForm account={modal.account} roles={roles} onClose={() => setModal(null)} /> : null}
      </Dialog>
    </div>
  );
}
