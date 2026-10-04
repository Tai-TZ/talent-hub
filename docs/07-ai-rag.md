# Thiết kế AI: trợ lý RAG, chấm sơ bộ, báo cáo cải tiến

## 1. Nguyên tắc
- AI **chỉ gợi ý**, không đổi trạng thái hồ sơ, không ra quyết định.
- Mọi câu trả lời của trợ lý phải có trích nguồn hoặc từ chối.
- Không gửi dữ liệu cá nhân sang LLM trừ khi tác vụ cần (chấm sơ bộ) và đợt tuyển đã bật; khi gửi thì loại trường nhạy cảm.
- Mọi lần gọi LLM ghi lại provider, model, phiên bản prompt, số token, độ trễ.

## 2. Lớp provider

```python
class LLMProvider(Protocol):
    async def chat(self, messages: list[Message], *, model: str, stream: bool = False,
                   response_schema: dict | None = None, temperature: float = 0.0) -> ChatResult | AsyncIterator[Chunk]: ...

class EmbeddingProvider(Protocol):
    dimensions: int
    async def embed(self, texts: list[str]) -> list[list[float]]: ...

class Reranker(Protocol):          # tuỳ chọn
    async def rerank(self, query: str, docs: list[str], top_n: int) -> list[int]: ...
```

Cấu hình theo tác vụ trong `settings`:

```
LLM_CHAT_PROVIDER=anthropic      LLM_CHAT_MODEL=...
LLM_SCORING_PROVIDER=...         LLM_SCORING_MODEL=...
LLM_REPORT_PROVIDER=...          LLM_REPORT_MODEL=...
EMBEDDING_PROVIDER=...           EMBEDDING_MODEL=...   EMBEDDING_DIM=...
```

Triển khai: `anthropic`, `openai`, `gemini`, `ollama`, và `fake` (trả lời xác định để chạy test và demo không cần API key). API key đọc từ biến môi trường, không lưu DB. Nếu thiếu key thì tính năng AI tắt và UI hiển thị rõ, phần còn lại của hệ thống vẫn chạy.

## 3. Trợ lý hỏi đáp (RAG)

### Nạp tài liệu
1. Admin upload PDF/DOCX/MD hoặc URL → `kb_documents` trạng thái `processing`.
2. Worker trích văn bản (giữ cấu trúc heading), chia chunk theo heading, tối đa ~500 token, chồng lấp ~60 token; mỗi chunk mang `heading_path` để trích nguồn rõ ràng.
3. Tính embedding theo lô, ghi `kb_chunks` (kèm `tsv`). Xong thì `ready`; lỗi thì `failed` kèm lý do.
4. Tài liệu mới phiên bản: tạo document version mới, chunk cũ chuyển `retired` sau khi bản mới `ready`.

### Truy vấn
1. Kiểm tra quyền và rate limit (ví dụ 20 câu/giờ/người dùng).
2. Chuẩn hoá câu hỏi; nếu nằm trong hội thoại, viết lại thành câu hỏi độc lập.
3. **Hybrid retrieval**: top 30 theo vector (cosine) + top 30 theo full-text, hợp nhất bằng Reciprocal Rank Fusion; lọc theo `visibility` được phép.
4. Rerank (nếu bật) còn top 6.
5. Nếu điểm tốt nhất dưới ngưỡng → trả lời từ chối cố định: "Mình chưa tìm thấy thông tin này trong tài liệu tuyển sinh. Bạn có thể liên hệ …" (không gọi LLM).
6. Gọi LLM với prompt hệ thống: chỉ dùng ngữ cảnh được cấp, mỗi ý quan trọng gắn `[n]`, không suy đoán, trả lời cùng ngôn ngữ người hỏi.
7. **Kiểm tra sau sinh**: mọi `[n]` phải trỏ tới chunk được cấp; câu trả lời không có citation nào bị coi là không đạt và trả về dạng từ chối.
8. Stream về client kèm danh sách nguồn (tên tài liệu, mục, đoạn trích ngắn).

### Chống lạm dụng
- Nội dung tài liệu và câu hỏi người dùng luôn nằm trong khối dữ liệu, prompt hệ thống nói rõ không làm theo chỉ dẫn xuất hiện trong ngữ cảnh (chống prompt injection qua tài liệu).
- Không có công cụ (tool) nào cho trợ lý ghi dữ liệu hay đọc dữ liệu hồ sơ; trợ lý chỉ đọc kho tri thức.
- Lọc PII cơ bản (số điện thoại, CCCD) khỏi log.

### Đánh giá
- `rag_eval_cases`: tối thiểu 50 câu hỏi thật về quy trình tuyển sinh, kèm tài liệu mong đợi.
- Chỉ số: recall@6 (tài liệu đúng nằm trong top 6), tỉ lệ citation hợp lệ, tỉ lệ từ chối đúng với câu hỏi ngoài phạm vi, độ trung thực (LLM-as-judge, kiểm tay mẫu 10%).
- Ngưỡng bật cho người dùng thật: recall@6 ≥ 0.85, citation hợp lệ ≥ 0.95, từ chối đúng ≥ 0.9. Chạy lại mỗi khi đổi model, prompt hoặc chiến lược chia chunk.

## 4. Chấm sơ bộ hồ sơ (tuỳ chọn theo đợt)
- Bật bằng `intakes.ai_screening_enabled` và ứng viên được thông báo khi nộp.
- Đầu vào: chỉ các trường cần cho rubric (học vấn, kinh nghiệm, bài luận, dự án). Loại tên, ngày sinh, giới tính, ảnh, địa chỉ, CCCD, trường dữ liệu nhạy cảm khác. Danh sách trường đã dùng lưu ở `ai_assessments.input_fields`.
- Đầu ra bắt buộc theo JSON schema: điểm từng tiêu chí, trích dẫn bằng chứng trong hồ sơ, độ tin cậy, các điểm cần reviewer kiểm tra.
- Hiển thị cho reviewer **sau khi** reviewer đã chốt điểm của mình, kèm cảnh báo "chỉ mang tính tham khảo".
- Theo dõi độ lệch giữa điểm AI và điểm reviewer theo thời gian; lệch lớn bất thường thì báo admin.

## 5. Báo cáo cải tiến chương trình
1. Worker gom số liệu cấp chương trình: attainment từng chuẩn đầu ra theo khoá, xu hướng, các môn kéo thấp, chuẩn đầu ra thiếu bài đo, cảnh báo mở.
2. Gửi LLM chỉ số liệu **đã tổng hợp** (không có dữ liệu từng học viên), yêu cầu: tóm tắt, vấn đề chính kèm số liệu dẫn chứng, đề xuất hành động ưu tiên.
3. Kiểm tra sau sinh: mọi con số trong báo cáo phải khớp `metrics_snapshot` (so khớp bằng regex trên các số xuất hiện; không khớp thì đánh dấu để người duyệt kiểm tra).
4. Lưu `draft`; training manager chỉnh sửa và duyệt; từ báo cáo tạo `improvement_actions`.

## 6. Cảnh báo chất lượng dữ liệu (rule-based)

| Mã rule | Điều kiện | Mức |
|---|---|---|
| `missing_required_result` | Học viên không có điểm bài bắt buộc quá N ngày sau hạn | medium |
| `outcome_without_assessment` | Chuẩn đầu ra không có bài nào map tới | high |
| `weights_invalid` | Tổng trọng số map của một bài vượt giới hạn hoặc bằng 0 | medium |
| `score_out_of_range` | Điểm < 0 hoặc > max | high |
| `distribution_outlier` | Phân bố điểm một bài lệch > 3 độ lệch chuẩn so với trung bình các khoá trước | medium |
| `attainment_drop` | Tỉ lệ đạt chuẩn đầu ra giảm > 15 điểm % so với khoá trước | high |
| `lms_sync_failing` | Đồng bộ LMS thất bại ≥ 3 lần liên tiếp | high |
| `stale_data` | Không có điểm mới từ LMS quá 14 ngày trong học kỳ | low |

Mỗi alert có `fingerprint` để không tạo trùng khi rule chạy lại; alert tự đóng khi điều kiện hết.
