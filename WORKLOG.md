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
| Chất lượng chương trình (`/analytics/quality`): chuẩn đầu ra theo năng lực/nhánh, so khoá trước, cảnh báo dữ liệu thiếu/bất thường, đề xuất cải tiến, báo cáo Markdown | Xong (BE + FE), song ngữ |
| LLM: Claude hoặc chuẩn OpenAI (OpenRouter mặc định, OpenAI, Gemini) qua `LLM_API_KEY` | Xong, test bằng client giả; **chưa chạy với khoá thật** |
| Giao diện tiếng Anh | Nền tảng xong (`defineMessages`, `useT`, `useFormat`, `useLabels`); đã dịch thanh đầu trang, menu, Phân tích, Rubric Lab, Chất lượng chương trình. **Còn lại** ~850 dòng ở các khu ứng viên, nhân sự, khoá học, đợt tuyển, quản trị và thông báo lỗi backend |
| Quản trị IT: tài khoản (mời, nhập hàng loạt, khoá), tài liệu, chi phí, cài đặt, tổng quan | Xong (BE + FE) |
| Trợ lý hỏi đáp có trích nguồn + bộ đánh giá | Xong; động cơ offline đo được, động cơ LLM chưa đo |
| Hồ sơ năng lực có chữ ký (Skill Passport) | **Chưa làm** |
| Trang giới thiệu công khai (`/`) | Chưa làm |

Chất lượng hiện tại: backend 248 test, độ phủ 95%, ruff/mypy sạch; frontend 27 test đơn vị + 58 kịch bản e2e (chạy 72, 14 bỏ qua có chủ đích) (desktop và mobile, gồm quét trợ năng WCAG A/AA); semgrep, pip-audit, npm audit đều sạch.

## Đã đo (số thật, tái lập được)

- **Độ trễ API** (`backend/tools/bench_api.py`, ~1.700 hồ sơ, đợt lớn nhất 600): p95 dưới 40 ms cho các màn đọc; Rubric Lab 328 ms; Composer cho một khoá 160 ms; báo cáo xét đạt giảm 520 ms → 37 ms sau khi gộp truy vấn.
- **Sàng lọc AI offline ở quy mô 20.000 hồ sơ** (đo 05/10/2026 trên cùng máy, DB nhân bản): mã cũ 209 giây (95 hồ sơ/giây) → nay **khoảng 9–10 giây (~2.000 hồ sơ/giây)**, qua API thật (`uvicorn --reload`) job xong trong 9,3 giây. Kết quả ghi vào DB **giống hệt từng dòng** với mã cũ (20.000/20.000). Trong lúc chạy, API khác vẫn phản hồi: `GET /me` p50 17 ms, tối đa 176 ms. Đã làm:
  - Động cơ luật: lọc từ khoá bằng tìm chuỗi con trước regex đã biên dịch sẵn; `find_span` có đường nhanh không biên dịch regex cho mỗi trích dẫn (test đối chiếu ngẫu nhiên với regex gốc).
  - Ghi kết quả bằng `INSERT` nhiều dòng theo lô 500 (hoặc mỗi 2 giây), tiến độ cập nhật chung giao dịch (trước: mỗi 25 hồ sơ một session + ORM).
  - Đợt từ 1.000 hồ sơ chấm bằng động cơ luật trong `ProcessPoolExecutor` (`TRIAGE_WORKERS`, mặc định 4; 0 = tắt), dò trùng chạy song song.
  - Một truy vấn duy nhất, nội dung lấy dạng chuỗi JSON (giải mã ở tiến trình con): giảm khựng do GC từ 230–340 ms xuống ~50 ms.
  - Ghi chú đo: CPU laptop hạ xung sau vài giây chạy nặng nên số tuyệt đối dao động; so sánh trước/sau luôn đo cùng điều kiện.
- **Độ trễ API trên đợt 20.000 hồ sơ** (`bench_api.py --org scale`, DB nhân bản từ DB dev, mỗi hồ sơ một lượt chấm): mọi màn p95 dưới 300 ms. Chậm nhất: báo cáo xét đạt p95 ~276 ms, lọc hàng đợi "ưu tiên xem kỹ" ~163 ms, bảng triage ~111 ms. Composer trả 409 ở tổ chức `scale` vì không có học viên đang học (dữ liệu, không phải lỗi).
- **Rubric Lab** (12.500 hồ sơ, 6.000 học viên có kết quả): p95 1.839 ms → **49 ms**; lần đầu (chưa có bộ nhớ đệm) ~500 ms. Đã làm: bootstrap 200 mẫu giải đồng thời bằng trọng số đếm + khởi động ấm (`bootstrap_coefs`); chỉ lấy trường cần và tính trung bình điểm trong SQL; bộ nhớ đệm trong tiến trình theo dấu vân tay dữ liệu (số dòng + tổng `updated_at` của hồ sơ, bài chấm, ghi danh), nên chỉnh trọng số không phân tích lại. Đầu ra đối chiếu giống hệt bản cũ (dữ liệu thật hai tổ chức + 40 bộ ngẫu nhiên). **Sửa lỗi có sẵn**: truy vấn thiếu `ORDER BY` làm khoảng tin cậy đổi giữa các lần xem.
- Lưu ý: bảng triage và bộ lọc hàng đợi chọn "lượt chấm mới nhất" bằng `DISTINCT ON`/truy vấn con trên mọi lượt chấm; mỗi lần sàng lọc lại có `force` thêm 20.000 dòng nên chậm dần (đo được ~590 ms và ~965 ms khi mỗi hồ sơ có ~8 lượt chấm).
- **Trợ lý hỏi đáp** (`eval/README.md`): bộ phát triển 100% (đã tinh chỉnh theo bộ này nên không có ý nghĩa thước đo); **bộ giữ riêng 71% câu có đáp án đúng, 88% câu không có đáp án được từ chối đúng, 91% chính xác khi đã trả lời**. Các câu trượt đều là từ chối an toàn do khác từ đồng nghĩa.

## Lỗi thật tìm được qua các vòng QA (đã sửa)

- Kiểm tra bảo mật: con trỏ phân trang sai gây 500 (hàng đợi, nhật ký); `%`/`_` trong ô tìm kiếm bị hiểu là ký tự đại diện; 4 endpoint theo `cohort_id` trả 200 rỗng cho khoá của tổ chức khác thay vì 404.
- UX: nút nổi "Hỏi trợ lý" che nút "Tiếp tục" trên điện thoại; "Đăng xuất" xuống dòng; hàng 6 bước chiếm 6 dòng; thông báo lưu rubric biến mất do dựng lại form; chữ phụ không đủ tương phản (nâng `--th-text-muted` lên #6e6e6e để đạt AA).
- Thiết kế: seed minh hoạ tạo email trùng khi nạp ở hai tổ chức (nay email theo tổ chức); phạt cụm hai từ trong trợ lý làm trợ lý nhút nhát, đã thử rồi hoàn tác.

## Việc tiếp theo (theo thứ tự nên làm)

**Đối chiếu đề bài (05/10):** MVP đủ. Nâng cao: trợ lý có trích nguồn ✅, chuẩn đầu ra + cảnh báo dữ liệu + báo cáo cải tiến ✅ (trang Chất lượng chương trình). Còn thiếu theo công nghệ đề bài nêu tên: **Power BI** (schema `analytics` + role chỉ đọc + export CSV), **tích hợp CRM/LMS qua API**, **Docker đủ stack + triển khai cloud**; và sản phẩm nộp bài (JOURNAL, sơ đồ kiến trúc, bài trình bày, tự chấm 10 tiêu chí). Ưu tiên các mục này trước các mục dưới.

1. **Giữ hiệu năng khi sàng lọc lại nhiều lần** (tuỳ chọn, chưa gấp): đánh dấu lượt chấm mới nhất (ví dụ cột `is_latest` có chỉ mục một phần, hoặc xoá/lưu trữ lượt cũ khi chấm lại có `force`) để bảng triage và hàng đợi không chậm dần. Báo cáo xét đạt (p95 ~276 ms) sát ngưỡng 300 ms. Đo bằng `python tools/bench_api.py --org scale` trên DB nhân bản.
2. **Vòng QA 6 (nghiệp vụ)**: viết kiểm thử bất biến (không vượt chỉ tiêu, bốn mắt, chấm mù, điểm AI chỉ cho người có `triage.read`) chạy với dữ liệu ngẫu nhiên; rà lại trải nghiệm bàn phím cho mọi hộp thoại.
3. **Skill Passport**: chứng nhận hoàn thành ký Ed25519 (khoá theo tổ chức), trang xác minh công khai `/verify/[id]`, huỷ/thu hồi, hiển thị trong trang học viên. Đây là phần "khó sao chép" cho đối tác doanh nghiệp.
4. **Trợ lý với Claude thật**: đặt `ANTHROPIC_API_KEY` trong `backend/.env`, chạy `eval-assistant --engine llm` trên bộ giữ riêng và so sánh; thêm bộ phân loại ý định (câu hỏi tra cứu so với yêu cầu thực hiện tác vụ hoặc dò dữ liệu cá nhân).
5. **Đa tổ chức đúng nghĩa cho đăng nhập**: link lời mời dựng từ `PUBLIC_BASE_URL` toàn cục, cần theo tên miền con của từng tổ chức; cấu hình Microsoft đang là toàn cục (`MICROSOFT_CLIENT_ID/SECRET`), cần bảng kết nối IdP theo tổ chức (xem `docs/09-multi-tenancy.md`).
6. **Hạ tầng thử nghiệm**: e2e đang ghi dữ liệu vào DB dev (đợt "E2E…", tài khoản thử). Cần DB riêng cho e2e (`talenthub_e2e`) với lệnh `make e2e-db` và `make run-be-e2e`. Cách tạm đã dùng ngày 05/10 (52 qua, 14 bỏ qua có chủ đích gồm 10 kịch bản Microsoft): `docker exec talent-hub-postgres-1 psql -U postgres -c "CREATE DATABASE talenthub_e2e_tmp TEMPLATE talenthub"`, chạy backend cổng 8000 với `DATABASE_URL`/`MIGRATION_DATABASE_URL` trỏ vào DB đó, `npm --prefix frontend run e2e`, rồi `DROP DATABASE talenthub_e2e_tmp`.
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
