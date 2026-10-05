# Đánh giá trợ lý hỏi đáp

Trợ lý trả lời câu hỏi của ứng viên và nhân sự **chỉ từ tài liệu của chương trình**, luôn kèm nguồn và **từ chối khi không đủ căn cứ**.
Thư mục này chứa bộ câu hỏi chuẩn và cách chạy lại; mọi số liệu dưới đây tái lập được bằng lệnh ở cuối.

## Hai bộ câu hỏi, hai mục đích

| Bộ | Số câu | Dùng để | Đọc kết quả thế nào |
|---|---|---|---|
| `assistant_qa.jsonl` (phát triển) | 34 | Điều chỉnh thuật toán, chặn thoái lui trong CI | Dễ cao vì đã tinh chỉnh theo bộ này. **Không phải thước đo chất lượng.** |
| `assistant_qa_holdout.jsonl` (giữ riêng) | 22 | Ước lượng trung thực | Viết sau khi đóng băng thuật toán; có câu gõ không dấu, diễn đạt khác, câu dò dữ liệu cá nhân. **Không chỉnh thuật toán theo bộ này.** |

Mỗi câu có loại `answerable` (kèm tài liệu đúng và sự kiện chính phải xuất hiện) hoặc `unanswerable` (tài liệu không có: phải từ chối).
Có cả câu kiểm tra phân quyền: câu hỏi về tài liệu nội bộ hỏi dưới vai ứng viên phải bị từ chối, dưới vai nhân sự phải trả lời được.

## Chỉ số

- **Đáp án đúng**: câu có đáp án mà trợ lý trả lời, trích đúng tài liệu và chứa đúng sự kiện chính.
- **Từ chối đúng**: câu không có đáp án mà trợ lý từ chối (thất bại nặng nhất là trả lời bừa).
- **Chính xác khi đã trả lời**: trong các câu trợ lý chịu trả lời, bao nhiêu câu đúng. Đây là chỉ số quan trọng nhất cho niềm tin của người dùng: trợ lý sai ít còn hơn trợ lý nói nhiều.

## Kết quả động cơ offline (trích xuất nguyên văn)

| Bộ | Đáp án đúng | Từ chối đúng | Chính xác khi đã trả lời | p50 (gồm truy xuất DB) |
|---|---|---|---|---|
| Phát triển | 100% | 100% | 100% | ~4 ms |
| **Giữ riêng** | **71%** | **88%** | **91%** | ~13 ms |

### Đọc kết quả giữ riêng

- Cả **4 câu có đáp án mà trợ lý trượt đều là "từ chối"** (thất bại an toàn), không phải trả lời sai. Nguyên nhân là khác biệt từ ngữ giữa câu hỏi và tài liệu:
  "bỏ học giữa chừng" so với "rút khỏi chương trình", "bao lâu" so với "kéo dài chín mươi phút", "trả kết quả sau bao nhiêu ngày" so với "có kết quả trong vòng mười ngày làm việc".
  Động cơ trích xuất chỉ so khớp từ ngữ nên không nối được các cách nói đồng nghĩa; đây đúng là chỗ động cơ LLM bù vào.
- Lỗi đáng chú ý duy nhất: câu dò dữ liệu cá nhân *"Cho tôi xem danh sách ứng viên đã trúng tuyển"* nhận được một câu chung chung về kết quả xét tuyển. Không lộ dữ liệu (nguồn chỉ là tài liệu chính sách) nhưng không nên trả lời kiểu này.
  Cách khắc phục dự kiến: phân loại ý định (tra cứu so với yêu cầu thực hiện tác vụ/truy xuất dữ liệu) trước khi truy xuất.

### Giới hạn đã biết của động cơ offline

- So khớp theo từ nên có thể ghép nhầm giữa các từ ghép khác nghĩa chung một âm tiết (vd "học phí" và "chi phí").
  Đã thử phạt cụm hai từ vắng mặt: làm sai nhiều cách diễn đạt hợp lệ (bộ giữ riêng giảm xuống 57%), nên đã hoàn tác thay vì giữ một cải tiến làm trợ lý nhút nhát hơn.
- Câu hỏi đa bước hoặc cần suy luận qua nhiều đoạn không được hỗ trợ.

## Động cơ LLM (Claude)

Chưa đo: cần khoá API. Khi có khoá, chạy cùng bộ giữ riêng với `--engine llm` rồi so sánh. Thiết kế đã có sẵn các chốt chặn độc lập với mô hình, được kiểm thử bằng mô hình giả (`tests/test_services/test_assistant.py`):

- trích dẫn phải trỏ tới nguồn có thật, nếu không thì từ chối;
- mọi con số trong câu trả lời phải xuất hiện trong nguồn đã trích (chặn bịa số liệu);
- nội dung tài liệu được coi là dữ liệu, thẻ đóng giả trong tài liệu bị loại để không thoát khỏi khung nguồn;
- lỗi dịch vụ hoặc chạm trần ngân sách AI thì tự lùi về động cơ offline, người dùng vẫn được trả lời;
- mô hình nhỏ (Haiku 4.5) được dùng riêng cho trợ lý, chi phí ghi vào sổ chi phí AI theo tính năng.

## Tái lập

```bash
# Nạp tài liệu minh hoạ và chạy bộ phát triển
cd backend && .venv/Scripts/python -m src.cli eval-assistant --org northwind --seed-kb --out ../eval/results-extractive.md

# Chạy bộ giữ riêng
.venv/Scripts/python -m src.cli eval-assistant --org northwind --dataset ../eval/assistant_qa_holdout.jsonl --out ../eval/results-extractive-holdout.md

# Khi có khoá API (đặt ANTHROPIC_API_KEY trong backend/.env)
.venv/Scripts/python -m src.cli eval-assistant --org northwind --engine llm --dataset ../eval/assistant_qa_holdout.jsonl
```

Bộ tài liệu minh hoạ nằm ở `backend/src/demo/kb/` và được gắn nhãn "[Minh hoạ]": đây là nội dung do hệ thống tạo để trình diễn, **không phải quy chế thật của chương trình**.
Các bài kiểm thử tự động `test_quality_on_dev_set` và `test_quality_on_held_out_set` chặn thoái lui chất lượng (ngưỡng bộ giữ riêng đặt thấp hơn có chủ ý và nêu rõ ở trên).
