# WORKLOG: trạng thái dự án và việc tiếp theo

Cập nhật lần cuối: 05/10/2026. Đây là ghi chú bàn giao để lần làm việc sau tiếp tục ngay, không phải dò lại.

## Đang ở đâu

Sản phẩm chạy được đầu-cuối trên máy local (Docker chỉ cho PostgreSQL). Mọi thứ dưới đây đã commit và đẩy lên GitHub.

| Mảng | Trạng thái |
|---|---|
| Nền tảng đa tổ chức (RLS), xác thực, phân quyền, nhật ký kiểm toán | Xong, có test |
| Đăng nhập: tài khoản do admin cấp (lời mời) và Microsoft (OIDC + PKCE, định danh theo issuer+subject, chống nOAuth) | Xong, có test; chưa thử với Entra thật (cần client id/secret) |
| Tuyển sinh: đợt tuyển, rubric, hồ sơ 6 bước tự lưu, chấm độc lập, phê duyệt bốn mắt, khoá AI chống neo | Xong (BE + FE), có e2e 4 vai trò |
| Sàng lọc AI hàng loạt có bằng chứng kiểm chứng nguyên văn | Xong; đang chạy bằng động cơ luật offline, chưa thử Claude thật |
| Vận hành khoá: ghi danh, Cohort Composer, mentor đánh giá năng lực, xét đạt, phụ cấp ↔ sổ chi phí | Xong (BE + FE), có test |
| Phân tích: phễu, giám sát công bằng, Rubric Lab | Xong (BE + FE) |
| Quản trị IT: tài khoản (mời, nhập hàng loạt, khoá), tài liệu, chi phí, cài đặt, tổng quan | Xong (BE + FE) |
| Trợ lý hỏi đáp có trích nguồn + bộ đánh giá | Xong; động cơ offline đo được, động cơ LLM chưa đo |
| Hồ sơ năng lực có chữ ký (Skill Passport) | **Chưa làm** |
| Trang giới thiệu công khai (`/`) | Chưa làm |

Chất lượng hiện tại: backend 186 test, độ phủ 94%, ruff/mypy sạch; frontend 23 test đơn vị + 58 kịch bản e2e (desktop và mobile, gồm quét trợ năng WCAG A/AA); semgrep, pip-audit, npm audit đều sạch.

## Đã đo (số thật, tái lập được)

- **Độ trễ API** (`backend/tools/bench_api.py`, ~1.700 hồ sơ, đợt lớn nhất 600): p95 dưới 40 ms cho các màn đọc; Rubric Lab 328 ms; Composer cho một khoá 160 ms; báo cáo xét đạt giảm 520 ms → 37 ms sau khi gộp truy vấn.
- **Sàng lọc AI offline ở quy mô 20.000 hồ sơ**: 184 giây (khoảng 108 hồ sơ/giây), 0 lỗi. Chạy được nhưng chậm so với kỳ vọng; xem việc tiếp theo số 1.
- **Trợ lý hỏi đáp** (`eval/README.md`): bộ phát triển 100% (đã tinh chỉnh theo bộ này nên không có ý nghĩa thước đo); **bộ giữ riêng 71% câu có đáp án đúng, 88% câu không có đáp án được từ chối đúng, 91% chính xác khi đã trả lời**. Các câu trượt đều là từ chối an toàn do khác từ đồng nghĩa.

## Lỗi thật tìm được qua các vòng QA (đã sửa)

- Kiểm tra bảo mật: con trỏ phân trang sai gây 500 (hàng đợi, nhật ký); `%`/`_` trong ô tìm kiếm bị hiểu là ký tự đại diện; 4 endpoint theo `cohort_id` trả 200 rỗng cho khoá của tổ chức khác thay vì 404.
- UX: nút nổi "Hỏi trợ lý" che nút "Tiếp tục" trên điện thoại; "Đăng xuất" xuống dòng; hàng 6 bước chiếm 6 dòng; thông báo lưu rubric biến mất do dựng lại form; chữ phụ không đủ tương phản (nâng `--th-text-muted` lên #6e6e6e để đạt AA).
- Thiết kế: seed minh hoạ tạo email trùng khi nạp ở hai tổ chức (nay email theo tổ chức); phạt cụm hai từ trong trợ lý làm trợ lý nhút nhát, đã thử rồi hoàn tác.

## Việc tiếp theo (theo thứ tự nên làm)

1. **Hiệu năng sàng lọc 20.000 hồ sơ**: đo nút cổ chai (`src/services/triage.py`: nạp nội dung, phát hiện trùng lặp bằng chỉ mục shingle, ghi từng cụm, `CHUNK`), mục tiêu từ 500 hồ sơ/giây. Sau đó chạy `python tools/bench_api.py --org scale` để đo hàng đợi, bảng triage, phân tích trên đợt 20.000 hồ sơ (tổ chức `scale` đã nạp sẵn trong DB dev và đã sàng lọc xong).
2. **Vòng QA 6 (nghiệp vụ)**: viết kiểm thử bất biến (không vượt chỉ tiêu, bốn mắt, chấm mù, điểm AI chỉ cho người có `triage.read`) chạy với dữ liệu ngẫu nhiên; rà lại trải nghiệm bàn phím cho mọi hộp thoại.
3. **Skill Passport**: chứng nhận hoàn thành ký Ed25519 (khoá theo tổ chức), trang xác minh công khai `/verify/[id]`, huỷ/thu hồi, hiển thị trong trang học viên. Đây là phần "khó sao chép" cho đối tác doanh nghiệp.
4. **Trợ lý với Claude thật**: đặt `ANTHROPIC_API_KEY` trong `backend/.env`, chạy `eval-assistant --engine llm` trên bộ giữ riêng và so sánh; thêm bộ phân loại ý định (câu hỏi tra cứu so với yêu cầu thực hiện tác vụ hoặc dò dữ liệu cá nhân).
5. **Đa tổ chức đúng nghĩa cho đăng nhập**: link lời mời dựng từ `PUBLIC_BASE_URL` toàn cục, cần theo tên miền con của từng tổ chức; cấu hình Microsoft đang là toàn cục (`MICROSOFT_CLIENT_ID/SECRET`), cần bảng kết nối IdP theo tổ chức (xem `docs/09-multi-tenancy.md`).
6. **Hạ tầng thử nghiệm**: e2e đang ghi dữ liệu vào DB dev (đợt "E2E…", tài khoản thử). Cần DB riêng cho e2e (`talenthub_e2e`) với lệnh `make e2e-db` và `make run-be-e2e`.
7. **Tài liệu và sản phẩm trình bày**: cập nhật `docs/05, 06, 08` theo thực tế (tên thư mục `backend/`, composer, lab, trợ lý, Microsoft); viết `JOURNAL.md`, `architecture_diagram`, bài trình bày; bảng tự chấm điểm 10 tiêu chí và trả lời 10 câu hỏi của đề bài; cập nhật bảng trạng thái trong README (đã sửa ở đợt này).
8. **Giao diện**: trang `/` giới thiệu chương trình cho ứng viên (kèm trợ lý), chuông thông báo trên thanh đầu trang, bản tiếng Anh cho khu nhân sự và quản trị (hiện chỉ tiếng Việt).
9. **CI**: thêm job e2e (dùng DB riêng + IdP giả), giữ semgrep và pip-audit; kiểm tra job frontend dùng `npm run api:types` để chặn lệch hợp đồng API.

## Cách chạy lại từ đầu

```bash
make db-up                 # PostgreSQL (Docker). Cần Docker Desktop đang chạy
make migrate && make seed  # lược đồ + tài khoản dev: <vai_trò>@northwind.test / Passw0rd!dev
cd backend && .venv/Scripts/python -m src.cli seed-demo --org northwind --current 600   # dữ liệu minh hoạ (giả, gắn nhãn)
make run-be                # http://localhost:8000
make run-fe                # http://localhost:3000
# Tuỳ chọn: đăng nhập Microsoft giả để dev/e2e
make run-idp               # cổng 9100
make run-be-idp            # backend bật Microsoft trỏ vào IdP giả
E2E_MICROSOFT=1 npm --prefix frontend run e2e
```

Kiểm tra trước khi đẩy: `make lint typecheck test-be test-fe`, và `make api-types` nếu đổi API (file kiểu của FE được sinh từ OpenAPI của BE).

## Lưu ý về môi trường dev hiện tại

- DB dev có dữ liệu thử lẫn: demo northwind (K1–K5), đợt K5 đã đóng và đã sàng lọc, nhiều đợt/tài khoản "E2E…", các lượt Composer do công cụ đo tạo ra, và tổ chức `scale` (khoảng 26.000 hồ sơ). Muốn sạch: `docker compose down -v`, rồi chạy lại các lệnh ở mục trên.
- Email demo nay theo tổ chức (`…@<tổ-chức>.demo.talenthub.invalid`); dữ liệu nạp trước thay đổi này dùng tên miền cũ.
- Next.js đang đặt `proxyClientMaxBodySize: 22mb` để nhận tệp tài liệu qua BFF. Khi triển khai thật, đặt thêm giới hạn kích thước theo route ở reverse proxy (nginx/ingress) để một request lớn không làm phình bộ nhớ.
- Rate limit dùng bộ nhớ trong khi local; cấu hình production bắt buộc `REDIS_URL` (có kiểm tra khi khởi động).
- Chưa cài hook ghi nhật ký sử dụng AI của repo mẫu vì nó tải lời nhắc lên máy chủ ngoài và cần khoá cá nhân của bạn; nếu cuộc thi yêu cầu, hãy tự cài với khoá của bạn.
