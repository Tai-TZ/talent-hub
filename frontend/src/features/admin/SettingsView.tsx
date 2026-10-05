"use client";

import { useState } from "react";
import { Alert } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import { SelectField } from "@/components/ui/Fields";
import { PageHeader } from "@/components/ui/Kit";
import { QueryState } from "@/components/ui/QueryState";
import { TextField } from "@/components/ui/TextField";
import type { SettingsT } from "@/lib/contracts";
import { errorText, useGet, useSend } from "@/lib/hooks";
import { SETTING_LABELS } from "@/lib/labels";

function Form({ initial, spec }: { initial: Record<string, unknown>; spec: Record<string, string> }) {
  const [values, setValues] = useState<Record<string, string>>(() => Object.fromEntries(Object.entries(initial).map(([k, v]) => [k, String(v)])));
  const [message, setMessage] = useState<{ tone: "success" | "danger"; text: string; fields?: Record<string, string> } | null>(null);
  const save = useSend<unknown, { values: Record<string, unknown> }>("PUT", "/admin/settings", { invalidate: ["/admin/settings", "/admin/overview", "/admin/costs"] });

  const dirty = Object.entries(values).some(([k, v]) => v !== String(initial[k]));

  function submit() {
    setMessage(null);
    const payload: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(values)) {
      if (v === String(initial[k])) continue;
      payload[k] = typeof initial[k] === "number" ? Number(v) : v;
    }
    save.mutate({ values: payload }, { onSuccess: () => setMessage({ tone: "success", text: "Đã lưu cài đặt." }), onError: (e) => setMessage({ tone: "danger", text: errorText(e), fields: e.fields }) });
  }

  return (
    <form
      className="th-card panel panel--form stack"
      onSubmit={(e) => {
        e.preventDefault();
        submit();
      }}
    >
      {Object.keys(spec).map((key) =>
        key === "ai_engine" ? (
          <SelectField key={key} label={SETTING_LABELS[key] ?? key} value={values[key] ?? ""} help={spec[key]} error={message?.fields?.[key]} onChange={(e) => setValues((v) => ({ ...v, [key]: e.target.value }))}>
            <option value="heuristic">Offline (heuristic) – không tốn chi phí</option>
            <option value="llm">LLM (Claude) – cần khoá API và ngân sách</option>
          </SelectField>
        ) : (
          <TextField key={key} label={SETTING_LABELS[key] ?? key} type="number" step="any" value={values[key] ?? ""} help={spec[key]} error={message?.fields?.[key]} onChange={(e) => setValues((v) => ({ ...v, [key]: e.target.value }))} />
        ),
      )}
      {message ? <Alert tone={message.tone}>{message.text}</Alert> : null}
      <div>
        <Button type="submit" loading={save.isPending} disabled={!dirty}>
          Lưu cài đặt
        </Button>
      </div>
    </form>
  );
}

export function SettingsView() {
  const query = useGet<SettingsT>("/admin/settings");
  return (
    <div className="stack">
      <PageHeader title="Cài đặt" subtitle="Tham số vận hành của tổ chức. Mọi thay đổi được ghi vào nhật ký kiểm toán." />
      <QueryState query={query} lines={5}>
        {(s) => <Form key={JSON.stringify(s.values)} initial={s.values} spec={s.spec} />}
      </QueryState>
      <Alert tone="info" title="Khoá API của nhà cung cấp AI">
        Khoá API được cấu hình ở biến môi trường của máy chủ (không lưu trong giao diện hay cơ sở dữ liệu). Khi chưa có khoá, hệ thống tự dùng chế độ sàng lọc offline.
      </Alert>
    </div>
  );
}
