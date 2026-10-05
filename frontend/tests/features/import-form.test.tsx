import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ImportForm } from "@/features/admin/UsersView";

const ONE = "an.nguyen@northwind.example.edu,Nguyễn Văn An,reviewer";
const TWO = `${ONE}\nbinh.tran@northwind.example.edu,Trần Thị Bình,mentor`;

function dryRun(rows: number) {
  return {
    dry_run: true,
    summary: { ok: rows, error: 0, created: 0 },
    rows: Array.from({ length: rows }, (_, i) => ({ row: i + 1, email: `u${i}@x.test`, status: "ok", error: null, invite_link: null })),
  };
}

afterEach(() => vi.unstubAllGlobals());

describe("ImportForm", () => {
  it("sửa danh sách sau khi kiểm tra thử thì phải kiểm tra lại mới tạo được", async () => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify(dryRun(1)), { status: 200, headers: { "content-type": "application/json" } }));
    vi.stubGlobal("fetch", fetchMock);
    render(
      <QueryClientProvider client={new QueryClient()}>
        <ImportForm onClose={() => {}} />
      </QueryClientProvider>,
    );
    const box = screen.getByLabelText(/Danh sách tài khoản/);
    fireEvent.change(box, { target: { value: ONE } });
    fireEvent.click(screen.getByRole("button", { name: "Kiểm tra trước" }));
    const create = await screen.findByRole("button", { name: "Tạo 1 tài khoản" });
    await waitFor(() => expect(create).toBeEnabled());

    fireEvent.change(box, { target: { value: TWO } });
    const stale = screen.getByRole("button", { name: /^Tạo \d+ tài khoản$/ });
    expect(stale).toBeDisabled();
    expect(stale).toHaveTextContent("Tạo 2 tài khoản");
    expect(fetchMock).toHaveBeenCalledTimes(1); // chưa gửi yêu cầu tạo nào
  });
});
