"use client";

import { useState, useSyncExternalStore } from "react";
import { useErrorText, useFormat, useT } from "@/components/providers";
import { Alert } from "@/components/ui/Alert";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { Checkbox } from "@/components/ui/Fields";
import { PageHeader, Tabs } from "@/components/ui/Kit";
import { QueryState } from "@/components/ui/QueryState";
import { TextField } from "@/components/ui/TextField";
import type { IntegrationKey, IntegrationKeyCreated } from "@/lib/contracts";
import { useGet, useSend } from "@/lib/hooks";
import { integrationMessages, SCOPES, type Scope } from "./integrations-messages";

const REFRESH = ["/integrations/keys"];
const DATASETS = ["applications", "enrollments", "competency_attainment"] as const;

/** Địa chỉ gốc của tổ chức đang xem (tên miền quyết định tổ chức), đọc sau khi gắn để không lệch SSR. */
const noSubscribe = () => () => {};

function useOrigin(): string {
  return useSyncExternalStore(
    noSubscribe,
    () => window.location.origin,
    () => "https://<tổ-chức>.example",
  );
}

function CopyButton({ text, label, done }: { text: string; label: string; done: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      className="link-button"
      onClick={() => {
        void navigator.clipboard.writeText(text).then(() => {
          setCopied(true);
          setTimeout(() => setCopied(false), 2000);
        });
      }}
    >
      {copied ? done : label}
    </button>
  );
}

function CodeBlock({ code }: { code: string }) {
  const m = useT(integrationMessages).guide;
  return (
    <div className="code-block">
      <div className="code-block__bar">
        <CopyButton text={code} label={m.copy} done={m.copied} />
      </div>
      {/* Vùng cuộn ngang phải nhận focus để người dùng bàn phím cuộn được (WCAG 2.1.1). */}
      <pre tabIndex={0} aria-label={m.codeLabel}>
        <code>{code}</code>
      </pre>
    </div>
  );
}

function ScopeBadges({ scopes }: { scopes: string[] }) {
  const m = useT(integrationMessages).scopes;
  return (
    <span className="scope-list">
      {scopes.map((s) => (
        <Badge key={s} tone={s === "crm.read" ? "warning" : s === "lms.write" ? "success" : "info"}>
          {m[s as Scope]?.label ?? s}
        </Badge>
      ))}
    </span>
  );
}

function CreateDialog({ open, onClose, onCreated }: { open: boolean; onClose: () => void; onCreated: (c: IntegrationKeyCreated) => void }) {
  const m = useT(integrationMessages);
  const errorText = useErrorText();
  const [name, setName] = useState("");
  const [scopes, setScopes] = useState<Scope[]>(["export.read"]);
  const [error, setError] = useState<string | null>(null);
  const create = useSend<IntegrationKeyCreated, { name: string; scopes: Scope[] }>("POST", "/integrations/keys", { invalidate: REFRESH });

  function submit() {
    setError(null);
    if (scopes.length === 0) return setError(m.form.pickScope);
    create.mutate(
      { name: name.trim(), scopes },
      {
        onSuccess: (c) => {
          setName("");
          setScopes(["export.read"]);
          onCreated(c);
        },
        onError: (e) => setError(errorText(e)),
      },
    );
  }

  return (
    <Dialog
      open={open}
      title={m.form.heading}
      onClose={onClose}
      footer={
        <div className="row-actions">
          <Button loading={create.isPending} disabled={name.trim().length < 3} onClick={submit}>
            {m.form.submit}
          </Button>
          <Button variant="tertiary" onClick={onClose}>
            {m.form.cancel}
          </Button>
        </div>
      }
    >
      <div className="stack">
        <TextField label={m.form.name} help={m.form.nameHelp} value={name} maxLength={120} required onChange={(e) => setName(e.target.value)} />
        <fieldset className="plain-fieldset stack">
          <legend className="th-field__label">{m.form.scopes}</legend>
          <p className="muted">{m.form.scopesHelp}</p>
          {SCOPES.map((s) => (
            <Checkbox
              key={s}
              checked={scopes.includes(s)}
              onChange={(e) => setScopes((cur) => (e.target.checked ? [...cur, s] : cur.filter((x) => x !== s)))}
              label={
                <span className="scope-option">
                  <strong>{m.scopes[s].label}</strong>
                  <span className="muted">{m.scopes[s].help}</span>
                </span>
              }
            />
          ))}
        </fieldset>
        {error ? <Alert tone="danger">{error}</Alert> : null}
      </div>
    </Dialog>
  );
}

function CreatedDialog({ created, onClose }: { created: IntegrationKeyCreated | null; onClose: () => void }) {
  const m = useT(integrationMessages).created;
  const origin = useOrigin();
  if (!created) return null;
  const sample = created.key.scopes.includes("export.read")
    ? `curl -H "Authorization: Bearer ${created.token}" \\\n  ${origin}/api/v1/integrations/exports/competency_attainment.csv`
    : created.key.scopes.includes("lms.read")
      ? `curl -H "Authorization: Bearer ${created.token}" \\\n  "${origin}/api/v1/integrations/lms/roster?cohort=K3"`
      : `curl -H "Authorization: Bearer ${created.token}" \\\n  "${origin}/api/v1/integrations/crm/applications?limit=50"`;
  return (
    <Dialog
      open
      title={m.heading}
      onClose={onClose}
      size="lg"
      footer={
        <Button onClick={onClose}>{m.done}</Button>
      }
    >
      <div className="stack">
        <Alert tone="warning">{m.warn}</Alert>
        <div className="secret">
          <code className="mono">{created.token}</code>
          <CopyButton text={created.token} label={m.copy} done={m.copied} />
        </div>
        <ScopeBadges scopes={created.key.scopes} />
        <p className="muted">{m.tryIt}</p>
        <CodeBlock code={sample} />
      </div>
    </Dialog>
  );
}

function KeysPanel() {
  const m = useT(integrationMessages);
  const f = useFormat();
  const errorText = useErrorText();
  const keys = useGet<IntegrationKey[]>("/integrations/keys");
  const [creating, setCreating] = useState(false);
  const [created, setCreated] = useState<IntegrationKeyCreated | null>(null);
  const [revoking, setRevoking] = useState<IntegrationKey | null>(null);
  const [error, setError] = useState<string | null>(null);
  const revoke = useSend<IntegrationKey, string>("POST", (id) => `/integrations/keys/${id}/revoke`, { invalidate: REFRESH });

  return (
    <section className="th-card panel stack" aria-labelledby="keys-title">
      <div className="panel-head">
        <h2 id="keys-title" className="th-type-h4">
          {m.keys.heading}
        </h2>
        <Button onClick={() => setCreating(true)}>{m.keys.create}</Button>
      </div>
      {error ? <Alert tone="danger">{error}</Alert> : null}
      <QueryState query={keys} lines={3}>
        {(list) =>
          list.length === 0 ? (
            <p className="muted">{m.keys.empty}</p>
          ) : (
            <table className="th-table responsive-table">
              <thead>
                <tr>
                  <th scope="col">{m.keys.name}</th>
                  <th scope="col">{m.keys.scopes}</th>
                  <th scope="col">{m.keys.lastUsed}</th>
                  <th scope="col">{m.keys.status}</th>
                  <th scope="col">
                    <span className="sr-only">{m.keys.actions}</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {list.map((k) => (
                  <tr key={k.id} data-revoked={k.revoked_at != null}>
                    <th scope="row" data-label={m.keys.name}>
                      <span className="key-name">
                        {k.name}
                        <code className="mono muted">thk_{k.prefix}_…</code>
                        <span className="muted">
                          {m.keys.created} {f.date(k.created_at)}
                        </span>
                      </span>
                    </th>
                    <td data-label={m.keys.scopes}>
                      <ScopeBadges scopes={k.scopes} />
                    </td>
                    <td data-label={m.keys.lastUsed}>{k.last_used_at ? f.ago(k.last_used_at) : <span className="muted">{m.keys.never}</span>}</td>
                    <td data-label={m.keys.status}>
                      <Badge tone={k.revoked_at ? "danger" : "success"}>{k.revoked_at ? m.keys.revoked : m.keys.active}</Badge>
                    </td>
                    <td data-label={m.keys.actions}>
                      {k.revoked_at ? null : (
                        <Button variant="tertiary" size="sm" onClick={() => setRevoking(k)}>
                          {m.keys.revoke}
                        </Button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )
        }
      </QueryState>

      <CreateDialog
        open={creating}
        onClose={() => setCreating(false)}
        onCreated={(c) => {
          setCreating(false);
          setCreated(c);
        }}
      />
      <CreatedDialog created={created} onClose={() => setCreated(null)} />
      <Dialog
        open={revoking != null}
        title={revoking ? m.revokeDialog.heading(revoking.name) : ""}
        onClose={() => setRevoking(null)}
        size="sm"
        footer={
          <div className="row-actions">
            <Button
              variant="danger"
              loading={revoke.isPending}
              onClick={() => {
                if (!revoking) return;
                setError(null);
                revoke.mutate(revoking.id, { onSuccess: () => setRevoking(null), onError: (e) => setError(errorText(e)) });
              }}
            >
              {m.revokeDialog.confirm}
            </Button>
            <Button variant="tertiary" onClick={() => setRevoking(null)}>
              {m.revokeDialog.cancel}
            </Button>
          </div>
        }
      >
        <p>{m.revokeDialog.body}</p>
      </Dialog>
    </section>
  );
}

function GuidePanel() {
  const m = useT(integrationMessages);
  const origin = useOrigin();
  const powerbi = `let
    BaseUrl = "${origin}",
    ApiKey = "thk_...",
    Load = (dataset as text) =>
        Csv.Document(
            Web.Contents(BaseUrl, [
                RelativePath = "/api/v1/integrations/exports/" & dataset & ".csv",
                Headers = [Authorization = "Bearer " & ApiKey]
            ]),
            [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]
        ),
    Attainment = Table.PromoteHeaders(Load("competency_attainment"), [PromoteAllScalars = true])
in
    Attainment`;
  const lms = `# Danh sách học viên của khoá / Cohort roster
curl -H "Authorization: Bearer $KEY" "${origin}/api/v1/integrations/lms/roster?cohort=K3"

# Đẩy kết quả đánh giá / Push assessments
curl -X POST -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \\
  ${origin}/api/v1/integrations/lms/assessments \\
  -d '{"items":[{"external_ref":"moodle-8812","candidate_code":"NW-K3-0042","competency_code":"programming","level":5}]}'`;
  const crm = `curl -H "Authorization: Bearer $KEY" \\
  "${origin}/api/v1/integrations/crm/applications?updated_since=2026-10-01T00:00:00Z&limit=200"
# → { "items": [...], "next_cursor": "..." }  lặp lại với ?cursor=<next_cursor>`;
  return (
    <section className="th-card panel stack" aria-labelledby="guide-title">
      <h2 id="guide-title" className="th-type-h4">
        {m.guide.heading}
      </h2>
      <Tabs
        items={[
          { id: "powerbi", label: m.guide.powerbi, content: <div className="stack"><p className="muted">{m.guide.powerbiHelp}</p><CodeBlock code={powerbi} /></div> },
          { id: "lms", label: m.guide.lms, content: <div className="stack"><p className="muted">{m.guide.lmsHelp}</p><CodeBlock code={lms} /></div> },
          { id: "crm", label: m.guide.crm, content: <div className="stack"><p className="muted">{m.guide.crmHelp}</p><CodeBlock code={crm} /></div> },
        ]}
      />
      <p className="muted">{m.guide.docs}</p>
      <div className="stack">
        <h3 className="th-type-h5">{m.downloads.heading}</h3>
        <p className="muted">{m.downloads.help}</p>
        <div className="row-actions">
          {DATASETS.map((d) => (
            <a key={d} className="th-button th-button--secondary th-button--sm" href={`/api/v1/integrations/exports/${d}.csv`} download>
              {m.downloads[d]}
            </a>
          ))}
        </div>
      </div>
    </section>
  );
}

export function IntegrationsView() {
  const m = useT(integrationMessages);
  return (
    <div className="stack">
      <PageHeader title={m.title} subtitle={m.subtitle} />
      <KeysPanel />
      <GuidePanel />
    </div>
  );
}
