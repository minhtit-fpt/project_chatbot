# Spec: Gợi ý hỏi tiếp khi câu hỏi còn rộng (guided selling)

> Trạng thái: CHỜ DUYỆT SPEC → sau đó viết plan triển khai (chưa code).
> Ngày tạo: 2026-06-24. Branch: `feat/guided-selling-suggestions` (nhánh từ `feat/answer-quality`).
> Bối cảnh kích hoạt: user muốn bot KHÔNG chỉ trả lời thẳng, mà sau khi đưa 2–3 sản phẩm
> liên quan thì gợi ý thêm vài câu hỏi về thông số khách hay quan tâm — kiểu chatbot bán
> hàng hiện đại — để dẫn dắt lọc dần nhu cầu.

## Mục tiêu & ràng buộc
- Câu hỏi RỘNG/mơ hồ ("có điều hòa nào tốt không", "tư vấn giúp em máy giặt") → trả 2–3 sản
  phẩm liên quan nhất, **rồi** gợi ý tối đa 3 câu hỏi về thông số quyết định mua hàng của
  đúng loại sản phẩm đó.
- Câu hỏi CỤ THỂ ("giá Daikin FVA100 bao nhiêu") → trả thẳng, KHÔNG gợi ý (tránh làm phiền).
- **KHÔNG** thêm lần gọi LLM, **KHÔNG** thêm heuristic riêng, **KHÔNG** tăng latency đáng kể.
- **CHỈ backend** — không đụng FE. Phải hiển thị được trên FE hiện tại (FE chỉ render
  `answer: list[str]`, có thay marker `{{HOTLINE}}`).
- GIỮ ràng buộc chống bịa giá/số liệu (gợi ý là CÂU HỎI, không phải dữ kiện → rủi ro thấp).

## Quyết định thiết kế đã chốt (qua brainstorming)
- **A — phạm vi:** chỉ kích hoạt khi câu hỏi rộng/mơ hồ.
- **B — nguồn gợi ý:** sinh kèm trong CHÍNH lần gọi LLM trả lời (không gọi riêng).
- Hệ quả hay: **việc phát hiện "câu rộng" được giao luôn cho model** trong cùng lần gọi —
  model tự quyết có xuất gợi ý hay không. Không cần heuristic phân loại riêng.
- **Đường truyền:** chỉ BE nên không làm chip/clickable. Nhúng gợi ý thành dòng text trong
  `answer` để FE hiện ngay; ĐỒNG THỜI thêm field `suggestions: list[str]` cho log/analytics
  và để FE tương lai nâng cấp chip.

## Hợp đồng output của model
Model trả lời sản phẩm bình thường; nếu (và chỉ nếu) yêu cầu còn rộng thì xuất thêm phần
gợi ý sau marker cố định:

```
<phần trả lời sản phẩm bình thường, nhiều dòng>

###GỢI_Ý###
- Phòng mình rộng khoảng bao nhiêu m² ạ?
- Anh/chị muốn loại Inverter tiết kiệm điện cho đỡ tốn không ạ?
- Ngân sách dự kiến tầm bao nhiêu ạ?
```

- BE tách tại `###GỢI_Ý###`: phần trên = `answer` sạch, phần dưới = danh sách gợi ý (mỗi
  dòng `- …`).
- KHÔNG có marker → câu cụ thể → `suggestions = []`.
- Parse fail-safe: marker rỗng / format lệch / lỗi → `suggestions = []`, answer giữ nguyên.

## Components & file đụng tới
- `rag/prompt_builder.py` — bổ sung khối "GỢI Ý HỎI TIẾP" vào `SYSTEM_PROMPT`:
  điều kiện CHỈ-KHI-RỘNG, marker `###GỢI_Ý###`, tối đa 3 câu, bám đúng loại sản phẩm vừa
  liệt kê, kèm 1 ví dụ có gợi ý + 1 ví dụ phản chứng (câu cụ thể → không gợi ý). Cũng nhắc
  với câu rộng nên nêu 2–3 mẫu liên quan nhất thay vì liệt kê tràn lan.
- `rag/suggestions.py` (MỚI, nhỏ, single-purpose):
  `split_answer_and_suggestions(raw: str) -> tuple[str, list[str]]`
  — cắt theo `config.SUGGESTIONS_MARKER`, lấy các dòng `- …` (tối đa `MAX_SUGGESTIONS`),
  strip; bỏ marker + phần gợi ý khỏi answer; không marker → `(raw, [])`.
- `rag/chat_engine.py` — sau khi có raw text từ model: gọi `split_answer_and_suggestions`.
  `answer_text` (sạch) dùng cho cache + log DB + field `answer`. Thêm `suggestions` vào
  result dict và vào cache entry. (Xem "Điểm nhạy" cho history.)
- `api/formatting.py` — `format_answer_with_suggestions(answer: str, suggestions: list[str])
  -> list[str]`: trả `format_answer_lines(answer)` + (nếu có suggestions) 1 dòng dẫn
  `config.SUGGESTIONS_LEAD_IN` + các dòng `- <gợi ý>` (đã qua làm sạch).
- `api/main.py` — `ChatResponse` thêm `suggestions: list[str] = []`; payload `answer` dựng
  bằng `format_answer_with_suggestions`, set thêm field `suggestions`.
- `test_chat.py` — in `suggestions` ở debug local cho dễ soi.

## Điểm nhạy — tương tác với history / query planner
Khi khách trả lời một câu gợi ý ("phòng 20m2"), đó là lượt FOLLOW-UP. Query planner
(`rag/query_rewriter.plan_search_queries`, đã có ở `feat/answer-quality`) cần ngữ cảnh để
viết lại "phòng 20m2" → "điều hòa cho phòng 20m2".

→ **Quyết định:** history (in-memory, dùng dựng `contents` đa lượt cho model + làm ngữ cảnh
planner) lưu answer **kèm phần gợi ý** để planner/model thấy "Bot đã hỏi: phòng bao nhiêu
m²? / Khách: 20m2". Trong khi đó field `answer` trả FE, cache, và log DB vẫn dùng answer
**sạch** + `suggestions` riêng. Đây là lựa chọn có chủ đích để khép đúng vòng dẫn dắt.

## Config (`config.py`)
- `MAX_SUGGESTIONS = 3`
- `SUGGESTIONS_MARKER = "###GỢI_Ý###"`
- `SUGGESTIONS_LEAD_IN = "Để tư vấn sát hơn, anh/chị cho em hỏi thêm:"`

## Tests (offline, không gọi API thật)
- `split_answer_and_suggestions`: có marker → tách đúng answer/suggestions + cap 3; không
  marker → `(raw, [])`; marker nhưng phần dưới rỗng/rác → `[]`; marker bị loại khỏi answer;
  nhiều dòng `- …` xen dòng trống → lọc đúng.
- `format_answer_with_suggestions`: có suggestions → có dòng dẫn + đủ dòng gợi ý; không có →
  chỉ các dòng answer (không dòng dẫn thừa).
- `chat_engine.answer`: stub model trả text có marker → result `suggestions` đúng, `answer`
  sạch (không chứa marker), history-turn chứa phần gợi ý; stub không marker → `suggestions=[]`.
- Cache: lượt đầu câu rộng được cache → cache hit trả lại cả `suggestions`.
- Guard prompt: `SYSTEM_PROMPT` chứa `###GỢI_Ý###` + cụm điều kiện "chỉ khi…rộng".

## Rủi ro
- **MEDIUM** — over-trigger (gắn gợi ý cả khi câu đã cụ thể). Giảm: prompt nêu rõ điều kiện
  + ví dụ phản chứng; gợi ý chỉ là text phụ, không phá answer.
- **LOW** — model quên marker / format lệch. Giảm: parse fail-safe → `[]`, answer nguyên vẹn.
- **LOW** — gợi ý lạc loại sản phẩm. Giảm: prompt buộc bám đúng sản phẩm vừa liệt kê.

## KHÔNG làm (YAGNI)
- Không chip/clickable (FE chưa đụng được) — chỉ thêm field `suggestions` để sẵn cho sau.
- Không bảng thông số tĩnh theo danh mục.
- Không lần gọi LLM riêng để sinh gợi ý.
- Không slot-filling bắt buộc khai báo trước khi trả lời.

## Thứ tự thực hiện (sẽ chi tiết hoá ở plan)
- **Phase 1:** `suggestions.py` + tests (TDD) → `format_answer_with_suggestions` + tests.
- **Phase 2:** wire vào `chat_engine.answer` (split + result + cache + history) + tests.
- **Phase 3:** `ChatResponse.suggestions` + payload `api/main.py` + `test_chat.py` debug.
- **Phase 4:** revise `SYSTEM_PROMPT` + guard test; smoke `python3 test_chat.py` API thật
  (câu rộng "tư vấn điều hòa" có gợi ý; câu cụ thể không gợi ý; trả lời câu gợi ý → planner
  viết lại đúng).

**Độ phức tạp: LOW–MEDIUM** (parse + wiring nhẹ; rủi ro chính nằm ở prompt).
