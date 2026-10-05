import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { useState } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { QueueView } from "@/features/staff/QueueView";

const INTAKES = [
  { id: "i-a", name: "Đợt A", status: "closed", quota: 10, counts: {}, rounds: [{ key: "portfolio", label: "Xét hồ sơ" }] },
  { id: "i-b", name: "Đợt B", status: "closed", quota: 10, counts: {}, rounds: [{ key: "interview", label: "Phỏng vấn" }] },
];

vi.mock("@/lib/use-intake-selection", () => ({
  useIntakeSelection: () => {
    const [id, setId] = useState("i-a");
    return { query: { status: "success", data: INTAKES, isPending: false, isError: false }, intakes: INTAKES, selected: INTAKES.find((i) => i.id === id), select: setId };
  },
}));
vi.mock("@/components/providers", async (orig) => ({
  ...(await orig<typeof import("@/components/providers")>()),
  useMe: () => ({ permissions: [] }),
}));
vi.mock("@/components/ui/QueryState", () => ({ QueryState: ({ children }: { children: () => React.ReactNode }) => <>{children()}</> }));

const urls: string[] = [];
beforeEach(() => {
  urls.length = 0;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      urls.push(String(url));
      return new Response(JSON.stringify({ items: [], next_cursor: null }), { status: 200, headers: { "content-type": "application/json" } });
    }),
  );
});
afterEach(() => vi.unstubAllGlobals());

describe("QueueView", () => {
  it("đổi đợt tuyển thì bỏ bộ lọc vòng của đợt cũ", async () => {
    render(
      <QueryClientProvider client={new QueryClient()}>
        <QueueView />
      </QueryClientProvider>,
    );
    fireEvent.change(screen.getByLabelText("Vòng"), { target: { value: "portfolio" } });
    await waitFor(() => expect(urls.some((u) => u.includes("intake_id=i-a") && u.includes("round=portfolio"))).toBe(true));

    fireEvent.change(screen.getByLabelText("Đợt tuyển"), { target: { value: "i-b" } });
    await waitFor(() => expect(urls.some((u) => u.includes("intake_id=i-b"))).toBe(true));
    expect(urls.filter((u) => u.includes("intake_id=i-b")).every((u) => !u.includes("round="))).toBe(true);
    expect(screen.getByLabelText("Vòng")).toHaveValue("");
  });
});
