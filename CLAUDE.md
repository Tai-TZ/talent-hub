# Talent Hub — hướng dẫn cho agent

Nền tảng tuyển sinh và quản lý chất lượng đào tạo, đa tổ chức. Khách hàng đầu tiên là Northwind University (chương trình 20.000 nhân tài AI). Tài liệu thiết kế ở `docs/` (bắt đầu từ `docs/02-architecture.md`, `docs/09-multi-tenancy.md`, `docs/10-sample-tenant.md`).

## Cấu trúc

| Thư mục | Vai trò |
|---|---|
| `backend/` | **BE**: FastAPI + SQLAlchemy async + PostgreSQL. Mã nguồn trong `backend/src` |
| `frontend/` | **FE**: Next.js 16 (App Router) + TypeScript, style Northwind University. Mã nguồn trong `frontend/src` |
| `db/init/` | SQL khởi tạo vai trò DB cho Postgres local |
| `docs/` | Thiết kế, research, quyết định kiến trúc |

Backend phân tầng: `src/api` (HTTP, không chứa nghiệp vụ) → `src/services` (nghiệp vụ, không import FastAPI) → `src/models` (ORM). Hạ tầng: `src/config.py`, `src/db.py`, `src/middleware.py`, `src/logging_config.py`.

## Lệnh thường dùng

```bash
make db-up migrate seed          # Postgres + Redis, migration, dữ liệu dev (<vai_trò>@northwind.test / Passw0rd!dev)
make run-be                      # http://localhost:8000 (Swagger ở /docs khi ENVIRONMENT=local)
make run-fe                      # http://localhost:3000
make check                       # lint + typecheck + test cả hai phía
cd backend && .venv/Scripts/python.exe -m pytest --cov     # cần Postgres chạy
cd frontend && npm run e2e       # cần backend chạy; để tránh 429 khi chạy e2e: LOGIN_RATE_LIMIT_PER_MINUTE=1000
```

## Quy tắc bắt buộc

1. **Cô lập tổ chức ở DB**: bảng thuộc tổ chức phải có `organization_id`, `ENABLE`+`FORCE ROW LEVEL SECURITY` và policy (dùng `enable_org_rls_sql` trong `src/db.py`). Test `test_tenancy_rls.py` fail nếu sót. Vai trò runtime `talenthub_app` không được là superuser/BYPASSRLS/chủ bảng.
2. Mọi truy vấn chạy trong session có ngữ cảnh tổ chức (`org_db` / `org_session`). Không tự tạo session ngoài các cách này.
3. Quyết định tuyển sinh do **con người** ra; AI chỉ gợi ý và không đổi trạng thái hồ sơ.
4. Không đưa email vào việc định danh Microsoft (lỗi nOAuth): dùng `iss`+`sub`.
5. Không log mật khẩu, token, cookie hay body yêu cầu. Lỗi trả theo RFC 9457, không lộ chi tiết nội bộ.
6. Thêm tính năng = thêm test (backend giữ độ phủ ≥ 85%; UI quan trọng có e2e desktop và mobile).
7. Next.js 16 khác bản cũ (`middleware` → `proxy.ts`, API bất đồng bộ). Đọc `frontend/node_modules/next/dist/docs/` trước khi viết code Next.
8. Style: chỉ dùng token ngữ nghĩa `--th-*` (ví dụ `--th-text-primary`), không dùng màu thô; mobile-first; giữ vòng focus.
9. Commit nhỏ, theo từng đợt có ý nghĩa; thông điệp tiếng Việt kiểu `feat(backend): …`.

## Công cụ cho agent (đã cấu hình trong repo)

- **CodeGraph** (`.codegraph/`, chạy `codegraph sync` sau khi sửa nhiều): dùng `codegraph_explore` trước khi grep/đọc file để hiểu mã.
- **LSP** (plugin `pyright-lsp`, `typescript-lsp`): định nghĩa, tham chiếu, chẩn đoán. Cần `pyright`, `typescript-language-server` trong PATH.
- **Context7** (plugin): tra tài liệu thư viện đúng phiên bản trước khi dùng API mới. Cần đăng nhập lần đầu qua `/mcp`.
- **Playwright** (plugin + `@playwright/test`): kiểm chứng UI thật, chụp màn hình desktop/mobile.
- **ast-grep** (`.mcp.json`, CLI `ast-grep`): tìm/sửa mã theo cấu trúc, an toàn hơn regex khi refactor hàng loạt.
- **Semgrep** (`.mcp.json`, CLI `semgrep`): quét bảo mật (`semgrep scan --config p/python --config p/typescript`).
- **Memory** (`.claude/memory/memory.jsonl`, không commit): đồ thị tri thức cục bộ cho quyết định và bối cảnh dài hạn.
- **Skills** (`frontend/.claude/skills`, cài bằng `npx autoskills`): thực hành tốt nhất cho Next/React/Vitest/Playwright/trợ năng.

Máy Windows: `.mcp.json` dùng `cmd /c npx …`. Máy macOS/Linux đổi `command` thành `npx`/`uvx` trực tiếp.
