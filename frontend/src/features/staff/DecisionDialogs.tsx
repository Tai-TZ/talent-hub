"use client";

import { useState, type ReactNode } from "react";
import { Alert } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { SelectField, TextArea } from "@/components/ui/Fields";
import { errorText, useSend } from "@/lib/hooks";
import { outcomeLabel } from "@/lib/labels";

const OUTCOMES = ["accepted", "waitlisted", "rejected"] as const;
const REFRESH = ["/staff/applications", "/staff/approvals", "/intakes", "/analytics"];

interface Props {
  open: boolean;
  onClose: () => void;
  onDone: () => void;
  version: number;
}

/** Form trong hộp thoại: Enter gửi, lỗi hiện ngay trong hộp thoại. Nội dung chỉ được dựng khi hộp thoại mở nên tự đặt lại khi đóng. */
function DialogForm({
  onClose,
  onSubmit,
  error,
  pending,
  confirm,
  disabled,
  tone = "primary",
  children,
}: {
  onClose: () => void;
  onSubmit: () => void;
  error: string | null;
  pending: boolean;
  confirm: string;
  disabled: boolean;
  tone?: "primary" | "danger";
  children: ReactNode;
}) {
  return (
    <form
      className="stack"
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit();
      }}
    >
      {children}
      {error ? <Alert tone="danger">{error}</Alert> : null}
      <div className="dialog__actions">
        <Button variant="secondary" onClick={onClose}>
          Huỷ
        </Button>
        <Button type="submit" variant={tone} loading={pending} disabled={disabled}>
          {confirm}
        </Button>
      </div>
    </form>
  );
}

function OutcomeSelect({ value, onChange, help }: { value: string; onChange: (v: string) => void; help?: string }) {
  return (
    <SelectField label="Kết quả" value={value} onChange={(e) => onChange(e.target.value)} help={help}>
      {OUTCOMES.map((o) => (
        <option key={o} value={o}>
          {outcomeLabel(o)[0]}
        </option>
      ))}
    </SelectField>
  );
}

// ---------- Yêu cầu bổ sung ----------

type InfoProps = Props & { applicationId: string };

export function RequestInfoDialog(props: InfoProps) {
  return (
    <Dialog open={props.open} title="Yêu cầu ứng viên bổ sung thông tin" onClose={props.onClose}>
      <RequestInfoForm {...props} />
    </Dialog>
  );
}

function RequestInfoForm({ applicationId, onClose, onDone, version }: InfoProps) {
  const [message, setMessage] = useState("");
  const [error, setError] = useState<string | null>(null);
  const send = useSend<unknown, { version: number; message: string }>("POST", `/staff/applications/${applicationId}/request-info`, { invalidate: REFRESH });
  return (
    <DialogForm
      onClose={onClose}
      error={error}
      pending={send.isPending}
      confirm="Gửi yêu cầu"
      disabled={message.trim().length < 10}
      onSubmit={() => send.mutate({ version, message }, { onSuccess: onDone, onError: (e) => setError(errorText(e)) })}
    >
      <p>Ứng viên sẽ nhận thông báo và được chỉnh sửa hồ sơ. Hãy nêu rõ cần bổ sung điều gì.</p>
      <TextArea label="Nội dung yêu cầu" required rows={4} maxLength={2000} value={message} onChange={(e) => setMessage(e.target.value)} help="Tối thiểu 10 ký tự." />
    </DialogForm>
  );
}

// ---------- Đề xuất ----------

export function ProposeDialog(props: InfoProps) {
  return (
    <Dialog open={props.open} title="Đề xuất quyết định" onClose={props.onClose}>
      <ProposeForm {...props} />
    </Dialog>
  );
}

function ProposeForm({ applicationId, onClose, onDone, version }: InfoProps) {
  const [outcome, setOutcome] = useState("accepted");
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const send = useSend<unknown, { version: number; outcome: string; reason: string }>("POST", `/staff/applications/${applicationId}/proposals`, { invalidate: REFRESH });
  return (
    <DialogForm
      onClose={onClose}
      error={error}
      pending={send.isPending}
      confirm="Gửi đề xuất"
      disabled={reason.trim().length < 20}
      onSubmit={() => send.mutate({ version, outcome, reason }, { onSuccess: onDone, onError: (e) => setError(errorText(e)) })}
    >
      <p>Đề xuất chuyển cho người phê duyệt. Người đề xuất không thể tự phê duyệt (nguyên tắc bốn mắt).</p>
      <OutcomeSelect value={outcome} onChange={setOutcome} />
      <TextArea label="Lý do" required rows={4} maxLength={4000} value={reason} onChange={(e) => setReason(e.target.value)} help="Nêu bằng chứng cụ thể từ hồ sơ và điểm chấm. Tối thiểu 20 ký tự." />
    </DialogForm>
  );
}

// ---------- Phê duyệt ----------

type DecisionProps = Props & { decisionId: string; proposedOutcome: string };

export function ApproveDialog(props: DecisionProps) {
  return (
    <Dialog open={props.open} title="Phê duyệt quyết định" onClose={props.onClose}>
      <ApproveForm {...props} />
    </Dialog>
  );
}

function ApproveForm({ decisionId, proposedOutcome, onClose, onDone, version }: DecisionProps) {
  const [outcome, setOutcome] = useState(proposedOutcome);
  const [reason, setReason] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState<string | null>(null);
  const send = useSend<unknown, { version: number; outcome: string; reason: string; applicant_message: string }>("POST", `/staff/decisions/${decisionId}/approve`, { invalidate: REFRESH });
  return (
    <DialogForm
      onClose={onClose}
      error={error}
      pending={send.isPending}
      confirm="Phê duyệt"
      disabled={reason.trim().length < 20 || message.trim().length < 10}
      onSubmit={() => send.mutate({ version, outcome, reason, applicant_message: message }, { onSuccess: onDone, onError: (e) => setError(errorText(e)) })}
    >
      <OutcomeSelect value={outcome} onChange={setOutcome} help={`Đề xuất ban đầu: ${outcomeLabel(proposedOutcome)[0]}.`} />
      {outcome !== proposedOutcome ? <Alert tone="warning">Bạn đang thay đổi so với đề xuất. Việc này được ghi vào nhật ký kiểm toán.</Alert> : null}
      <TextArea label="Lý do quyết định" required rows={3} maxLength={4000} value={reason} onChange={(e) => setReason(e.target.value)} help="Tối thiểu 20 ký tự." />
      <TextArea label="Lời nhắn gửi ứng viên" required rows={3} maxLength={4000} value={message} onChange={(e) => setMessage(e.target.value)} help="Ứng viên sẽ thấy nội dung này. Tối thiểu 10 ký tự; nên lịch sự và cụ thể." />
    </DialogForm>
  );
}

// ---------- Trả lại ----------

export function ReturnDialog(props: Props & { decisionId: string }) {
  return (
    <Dialog open={props.open} title="Trả lại để xem xét thêm" onClose={props.onClose}>
      <ReturnForm {...props} />
    </Dialog>
  );
}

function ReturnForm({ decisionId, onClose, onDone, version }: Props & { decisionId: string }) {
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);
  const send = useSend<unknown, { version: number; note: string }>("POST", `/staff/decisions/${decisionId}/return`, { invalidate: REFRESH });
  return (
    <DialogForm
      onClose={onClose}
      error={error}
      pending={send.isPending}
      confirm="Trả lại"
      disabled={note.trim().length < 10}
      onSubmit={() => send.mutate({ version, note }, { onSuccess: onDone, onError: (e) => setError(errorText(e)) })}
    >
      <p>Hồ sơ quay về vòng đang xét và người đề xuất được thông báo.</p>
      <TextArea label="Điều cần xem xét lại" required rows={4} maxLength={2000} value={note} onChange={(e) => setNote(e.target.value)} help="Tối thiểu 10 ký tự." />
    </DialogForm>
  );
}
