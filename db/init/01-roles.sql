-- Hai vai trò DB tách biệt (xem docs/09-multi-tenancy.md):
--   talenthub_owner: sở hữu bảng, chạy migration. Chỉ dùng cho Alembic.
--   talenthub_app:   vai trò runtime của API/worker. KHÔNG superuser, KHÔNG BYPASSRLS, không sở hữu bảng,
--                    nên mọi truy vấn đều bị RLS ràng buộc.
-- Mật khẩu dưới đây chỉ dành cho môi trường local.

CREATE ROLE talenthub_owner LOGIN PASSWORD 'owner' NOSUPERUSER NOBYPASSRLS;
CREATE ROLE talenthub_app   LOGIN PASSWORD 'app'   NOSUPERUSER NOBYPASSRLS;

GRANT ALL PRIVILEGES ON DATABASE talenthub TO talenthub_owner;
GRANT CONNECT ON DATABASE talenthub TO talenthub_app;

\connect talenthub

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS citext;
CREATE EXTENSION IF NOT EXISTS unaccent;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

GRANT ALL ON SCHEMA public TO talenthub_owner;
GRANT USAGE ON SCHEMA public TO talenthub_app;

-- Bảng do owner tạo ra sau này tự động cấp quyền DML cho vai trò app.
ALTER DEFAULT PRIVILEGES FOR ROLE talenthub_owner IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO talenthub_app;
ALTER DEFAULT PRIVILEGES FOR ROLE talenthub_owner IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO talenthub_app;
