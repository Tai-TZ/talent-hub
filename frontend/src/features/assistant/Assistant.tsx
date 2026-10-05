"use client";

import { useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";
import { useMe } from "@/components/providers";
import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { api, ApiError } from "@/lib/api";
import type { components } from "@/lib/api-types";
import { errorText } from "@/lib/hooks";

type Answer = components["schemas"]["AskOut"];

interface Message {
  id: string;
  question: string;
  answer?: Answer;
  error?: string;
  rating?: boolean;
}

const SUGGESTIONS = ["Điều kiện dự tuyển là gì?", "Phụ cấp hàng tháng là bao nhiêu?", "AI có quyết định ai trúng tuyển không?"];

/** Biến "... [1] [2]" trong câu trả lời thành chỉ số nguồn bấm được. */
function withCitations(text: string, onPick: (n: number) => void): ReactNode[] {
  return text.split(/(\[\d+\])/g).map((part, i) => {
    const m = /^\[(\d+)\]$/.exec(part);
    if (!m) return <span key={i}>{part}</span>;
    const n = Number(m[1]);
    return (
      <sup key={i}>
        <button type="button" className="cite" onClick={() => onPick(n)} aria-label={`Xem nguồn ${n}`}>
          {n}
        </button>
      </sup>
    );
  });
}

function Bubble({ message, onRate }: { message: Message; onRate: (helpful: boolean) => void }) {
  const [open, setOpen] = useState<number | null>(null);
  const a = message.answer;
  return (
    <li className="chat__turn">
      <p className="chat__q">{message.question}</p>
      {message.error ? (
        <p className="chat__a chat__a--error" role="alert">
          {message.error}
        </p>
      ) : a ? (
        <div className={`chat__a ${a.answered ? "" : "chat__a--declined"}`}>
          <p>{withCitations(a.answer, (n) => setOpen(open === n ? null : n))}</p>
          {a.citations.length > 0 ? (
            <ul className="plain-list chat__sources" aria-label="Nguồn trích dẫn">
              {a.citations.map((c) => (
                <li key={c.n}>
                  <button type="button" className="link-button" aria-expanded={open === c.n} onClick={() => setOpen(open === c.n ? null : c.n)}>
                    [{c.n}] {c.title.replace("[Minh hoạ] ", "")}
                    {c.heading ? ` › ${c.heading}` : ""}
                  </button>
                  {open === c.n ? <blockquote className="quote">{c.snippet}</blockquote> : null}
                </li>
              ))}
            </ul>
          ) : null}
          <div className="chat__rate">
            <span className="muted">Câu trả lời có giúp ích không?</span>
            <button type="button" className="chip" aria-pressed={message.rating === true} onClick={() => onRate(true)}>
              Có
            </button>
            <button type="button" className="chip" aria-pressed={message.rating === false} onClick={() => onRate(false)}>
              Chưa
            </button>
          </div>
        </div>
      ) : (
        <p className="chat__a muted" role="status">
          Đang tìm trong tài liệu…
        </p>
      )}
    </li>
  );
}

export function Chat() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const end = useRef<HTMLDivElement>(null);

  useEffect(() => {
    end.current?.scrollIntoView({ block: "end" });
  }, [messages]);

  async function ask(question: string) {
    const q = question.trim();
    if (q.length < 3 || busy) return;
    const id = crypto.randomUUID();
    setMessages((m) => [...m, { id, question: q }]);
    setText("");
    setBusy(true);
    try {
      const answer = await api<Answer>("/assistant/ask", { method: "POST", json: { question: q } });
      setMessages((m) => m.map((x) => (x.id === id ? { ...x, answer } : x)));
    } catch (e) {
      const message = e instanceof ApiError && e.status === 429 ? "Bạn hỏi hơi nhanh, vui lòng đợi một chút rồi hỏi tiếp." : errorText(e, "Chưa trả lời được lúc này. Vui lòng thử lại.");
      setMessages((m) => m.map((x) => (x.id === id ? { ...x, error: message } : x)));
    } finally {
      setBusy(false);
    }
  }

  async function rate(message: Message, helpful: boolean) {
    if (!message.answer) return;
    setMessages((m) => m.map((x) => (x.id === message.id ? { ...x, rating: helpful } : x)));
    try {
      await api(`/assistant/queries/${message.answer.id}/feedback`, { method: "POST", json: { helpful } });
    } catch {
      // Không đánh giá được thì thôi; không làm gián đoạn cuộc trò chuyện.
    }
  }

  function submit(e: FormEvent) {
    e.preventDefault();
    void ask(text);
  }

  return (
    <div className="chat">
      <div className="chat__log" role="log" aria-live="polite" aria-label="Cuộc trò chuyện">
        {messages.length === 0 ? (
          <div className="stack">
            <p>Mình trả lời dựa trên tài liệu của chương trình và luôn kèm nguồn. Nếu tài liệu không có thông tin, mình sẽ nói rõ thay vì đoán.</p>
            <div className="row-actions">
              {SUGGESTIONS.map((s) => (
                <button key={s} type="button" className="chip" onClick={() => void ask(s)}>
                  {s}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <ol className="plain-list chat__list">
            {messages.map((m) => (
              <Bubble key={m.id} message={m} onRate={(h) => void rate(m, h)} />
            ))}
          </ol>
        )}
        <div ref={end} />
      </div>
      <form className="chat__form" onSubmit={submit}>
        <label className="sr-only" htmlFor="assistant-input">
          Câu hỏi của bạn
        </label>
        <textarea
          id="assistant-input"
          className="th-textarea"
          rows={2}
          maxLength={500}
          value={text}
          placeholder="Ví dụ: Hồ sơ cần những gì?"
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            // Bộ gõ (Telex/VNI trên macOS, IME) dùng Enter để chốt chữ đang gõ: lúc đó không được gửi câu hỏi.
            // Safari báo isComposing = false ở phím chốt nhưng keyCode là 229.
            if (e.nativeEvent.isComposing || e.keyCode === 229) return;
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              void ask(text);
            }
          }}
        />
        <Button type="submit" loading={busy} disabled={text.trim().length < 3}>
          Gửi
        </Button>
      </form>
      <p className="muted chat__note">Trợ lý chỉ tra cứu tài liệu, có thể chưa đầy đủ. Hãy kiểm tra nguồn và liên hệ ban tuyển sinh với việc quan trọng. Đừng nhập thông tin cá nhân nhạy cảm.</p>
    </div>
  );
}

/** Nút nổi mở trợ lý hỏi đáp có trích nguồn. */
export function Assistant() {
  const me = useMe();
  const [open, setOpen] = useState(false);
  if (!me.permissions.includes("assistant.use")) return null;
  return (
    <>
      <button type="button" className="assistant-fab" onClick={() => setOpen(true)} aria-haspopup="dialog">
        Hỏi trợ lý
      </button>
      <Dialog open={open} title="Trợ lý hỏi đáp" size="md" onClose={() => setOpen(false)}>
        <Chat />
      </Dialog>
    </>
  );
}
