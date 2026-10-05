// Cấu hình phía server. Không import file này từ client component.
export const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8000";
export const BASE_DOMAIN = process.env.BASE_DOMAIN ?? "localhost";
// Tổ chức dùng khi chạy local mà host không có tên miền con (localhost:3000).
export const DEFAULT_ORG = process.env.DEFAULT_ORG ?? "northwind";
export const INTERNAL_PROXY_SECRET = process.env.INTERNAL_PROXY_SECRET;
export const BACKEND_TIMEOUT_MS = 15_000;
export const MAX_BODY_BYTES = 1_048_576;
// Tải tài liệu lên kho tri thức (tệp tối đa 15 MB, mã hoá base64 trong JSON). Khớp với giới hạn của backend.
export const MAX_UPLOAD_BODY_BYTES = 22 * 1024 * 1024;
