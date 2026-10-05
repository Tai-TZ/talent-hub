import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { LoginForm } from "@/components/LoginForm";
import { I18nProvider } from "@/components/providers";
import { getMessages } from "@/lib/i18n";

vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: vi.fn(), push: vi.fn(), refresh: vi.fn() }) }));

const vi_ = getMessages("vi");

function renderWith(errorCode?: string) {
  return render(
    <I18nProvider locale="vi">
      <LoginForm next="/dashboard" errorCode={errorCode} />
    </I18nProvider>,
  );
}

describe("LoginForm ?error=", () => {
  it("hiện đúng thông điệp của mã lỗi đã biết", () => {
    renderWith("account_exists");
    expect(screen.getByRole("alert")).toHaveTextContent(vi_.login.errors["account_exists"] ?? "");
  });

  it.each(["constructor", "toString", "__proto__", "hasOwnProperty", "không-có-mã-này"])(
    "mã lạ %s không làm sập trang mà hiện thông báo chung",
    (code) => {
      renderWith(code);
      expect(screen.getByRole("alert")).toHaveTextContent(vi_.login.errors["failed"] ?? "");
    },
  );

  it("không có mã thì không có cảnh báo", () => {
    renderWith();
    expect(screen.queryByRole("alert")).toBeNull();
  });
});
