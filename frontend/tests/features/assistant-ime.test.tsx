import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Chat } from "@/features/assistant/Assistant";

const fetchMock = vi.fn(async () => new Response(JSON.stringify({ answerable: false, answer: "", citations: [], log_id: null }), { status: 200, headers: { "content-type": "application/json" } }));

beforeEach(() => {
  fetchMock.mockClear();
  vi.stubGlobal("fetch", fetchMock);
  Element.prototype.scrollIntoView = vi.fn();
});
afterEach(() => vi.unstubAllGlobals());

describe("Chat: Enter và bộ gõ", () => {
  it("Enter để chốt chữ khi đang gõ dấu (IME) không gửi câu hỏi", () => {
    render(<Chat />);
    const box = screen.getByLabelText("Câu hỏi của bạn");
    fireEvent.change(box, { target: { value: "Hồ sơ cần nhữn" } });
    fireEvent.keyDown(box, { key: "Enter", isComposing: true });
    fireEvent.keyDown(box, { key: "Enter", keyCode: 229 });
    expect(fetchMock).not.toHaveBeenCalled();
    expect(box).toHaveValue("Hồ sơ cần nhữn");
  });

  it("Enter bình thường vẫn gửi, Shift+Enter thì không", () => {
    render(<Chat />);
    const box = screen.getByLabelText("Câu hỏi của bạn");
    fireEvent.change(box, { target: { value: "Hồ sơ cần những gì?" } });
    fireEvent.keyDown(box, { key: "Enter", shiftKey: true });
    expect(fetchMock).not.toHaveBeenCalled();
    fireEvent.keyDown(box, { key: "Enter" });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});
