# Plan: Nâng chất lượng trả lời (A retrieval đa-thực-thể · B planner query · C prompt linh hoạt)

> Trạng thái: ĐÃ THỰC HIỆN (2026-06-23) trên branch `feat/answer-quality` — 43 unit test xanh.
> Ngày tạo: 2026-06-23. Branch gốc: `feat/conversation-memory` → tách `feat/answer-quality`.
> Bối cảnh kích hoạt: user phản hồi "cách trả lời đang bị cứng ngắc, ko có sự tuỳ biến".
>
> Đã giao: query_rewriter `plan_search_queries` (cổng heuristic + JSON few-shot, fail-open);
> chat_engine `_merge_query_results` round-robin + carry-forward; config `MAX_SUBQUERIES`/
> `MAX_CONTEXT_DOCS`; SYSTEM_PROMPT khối "NGUYÊN TẮC LINH HOẠT" + so sánh một bên. Còn lại
> (thủ công): smoke `python3 test_chat.py` với API thật (Daikin vs Gree, follow-up công nghệ).

## Bằng chứng (root cause)

Hai ví dụ thật từ `test_chat.py`:

1. **So sánh** — `"so sánh điều hòa cây Daikin và Gree"` → bot trả "chưa có thông tin so sánh… liên hệ hotline".
   `[debug] Nguồn` chỉ có **5 Daikin cây, 0 Gree**. Kiểm tra index: vault CÓ **196 sản phẩm Gree**,
   trong đó **11 điều hòa cây Gree** (`dieu-hoa-cay-gree-48000btu…`, `…42000btu`, `…30000btu`…).
   → Retrieval một-embedding bị "Daikin cây" lấn át; câu này là **lượt đầu** nên query-rewrite không chạy.

2. **Follow-up công nghệ** — chỉ trả **3/5 model** rồi bail hotline.
   `[debug] Query viết lại` = **nguyên văn câu hỏi messy** → rewrite ECHO, không viết lại.
   Hệ quả: new-docs là tài liệu generic (Dieu-Hoa-Daikin, treo tường, ống gió) chiếm 5/8 slot,
   đẩy 2 model cây (carry-forward) ra ngoài cap `FOLLOWUP_CONTEXT_LIMIT=8` → còn 3.

Ba lỗi riêng biệt:
- **(A)** Retrieval không kéo đủ thực thể khi so sánh.
- **(B)** Query-rewrite vô hiệu (echo) + merge để new-docs generic chiếm slot.
- **(C)** System prompt over-refusal: blanket-refuse + bail hotline thay vì tổng hợp/so sánh từ tài liệu đang có; lặp khuôn bullet.

## Mục tiêu & ràng buộc
- Câu so sánh kéo tài liệu **cả 2 hãng** → so sánh theo tiêu chí.
- Follow-up sinh query sạch (hết echo) → trả đủ các model.
- Giọng linh hoạt: tổng hợp/so sánh từ tài liệu có, trả lời từng phần khi thiếu data, bớt bail hotline, bớt lặp khuôn.
- **GIỮ** ràng buộc chống bịa giá/số liệu.
- **KHÔNG** tăng latency câu thường (no LLM-call khi không cần).

---

## Hợp nhất A + B: "retrieval query planner"

`rag/query_rewriter.py`: đổi `rewrite_query → plan_search_queries(question, history, *, client, model) -> list[str]`.

**Cổng gọi LLM (giữ latency câu thường):**
- Follow-up (history ≠ rỗng) → gọi planner.
- Lượt đầu **và** phát hiện ý so sánh qua heuristic rẻ → gọi planner.
- Còn lại (câu thường lượt đầu) → trả `[question]`, KHÔNG tốn LLM-call.

**Heuristic so sánh** (chỉ là cổng gọi, planner mới quyết số query):
keywords `so sánh`, `vs`, `đối chiếu`, `khác nhau`, `nên chọn`, `nên mua`, `… hay …`.

**Planner LLM** (sửa echo bằng few-shot + JSON):
- Prompt yêu cầu trả **mảng JSON 1–3 query độc lập**.
- Câu so sánh → mỗi hãng/thực thể 1 query; câu thường → 1 query.
- Kèm 2 ví dụ few-shot (so sánh→2 query; follow-up messy→1 query sạch rút mã model từ history).
- Parse JSON strict; lỗi/rỗng → fallback `[question]` (fail-open, không chặn trả lời).

## Multi-query retrieval + merge cân bằng (`rag/chat_engine.py` `answer()`)
- `queries = plan_search_queries(...)`; `retriever.search()` cho **từng** query.
- Hàm mới `_merge_query_results(list_doc_lists, prev_docs, limit)`:
  **interleave round-robin** (hạng 0 mỗi query → hạng 1 mỗi query…) để cân bằng các hãng,
  dedupe theo `path`, rồi nối `prev_docs` (carry-forward) lấp tới `limit`.
- Thay `_merge_context_docs` (giữ logic carry-forward, tổng quát hoá cho nhiều query).
- "Daikin vs Gree" → `["điều hòa cây Daikin","điều hòa cây Gree"]` → ~4 + 4 (cap 8).
- Follow-up công nghệ → new-docs là model cây (không còn generic chiếm slot) → đủ 5 model.

## Config (`config.py`)
- `MAX_SUBQUERIES = 3`.
- Đổi tên `FOLLOWUP_CONTEXT_LIMIT → MAX_CONTEXT_DOCS = 8` (cap chung merge đa-query + carry-forward).
- `QUERY_REWRITE_MODEL` giữ `gemini-2.5-flash` (không dùng lite cho planner).

---

## (C) Revise SYSTEM_PROMPT (`rag/prompt_builder.py`)

> TÍCH HỢP, KHÔNG ghi đè block phân loại câu hỏi + giá "Liên hệ" đang có (uncommitted).

1. **So sánh:** dựa tài liệu có → so sánh theo tiêu chí (giá, công suất, công nghệ, tính năng, xuất xứ).
   Chỉ một bên dữ liệu → vẫn trình bày bên đó + nói rõ bên kia chưa có; KHÔNG từ chối toàn bộ.
2. **Bớt bail hotline:** chỉ dùng câu mẫu "chưa có thông tin… hotline" khi tài liệu HOÀN TOÀN không liên quan.
   Liên quan một phần → trả phần có + nêu ngắn phần thiếu.
3. **Chống lặp khuôn:** nêu điểm chung một lần, rồi chỉ nhấn KHÁC BIỆT từng mẫu.
4. **Trả lời từng phần:** chỉ có chi tiết một phần sản phẩm khách nhắc → trả phần đó, phần còn lại nói ngắn "chưa có chi tiết".
5. **GIỮ:** chỉ dùng dữ kiện trong tài liệu, KHÔNG bịa giá/số liệu; plain-text; rule giá "Liên hệ".

---

## Tests
- `query_rewriter`: empty-history normal → `[question]` (không gọi client); comparison kw lượt đầu → planner gọi, parse JSON list; JSON lỗi → fallback `[question]`; follow-up → gọi planner.
- merge: round-robin cân bằng 2 list, dedupe, cap, carry-forward lấp phần dư.
- `chat_engine.answer`: comparison lượt đầu → retriever nhận 2 sub-query, `sources` có cả 2 hãng (stub retriever trả theo query); follow-up cũ vẫn xanh (đổi monkeypatch `rewrite_query` → `plan_search_queries`).
- (C): verify thủ công qua `test_chat.py` (API thật) + 1 test đối kháng chống bịa.

## Rủi ro
- **HIGH** — nới prompt → hallucinate khi "cố so sánh". Giảm: giữ rõ "chỉ so sánh dữ kiện có trong tài liệu, không bịa", test đối kháng.
- **MEDIUM** — planner JSON flaky / latency câu so sánh. Giảm: few-shot, parse strict + fail-open, cap docs.
- **MEDIUM** — heuristic so sánh sót/nhầm. Giảm: heuristic chỉ là cổng; follow-up luôn qua planner.
- **LOW** — đổi tên `rewrite_query`/`FOLLOWUP_CONTEXT_LIMIT` vỡ test → cập nhật. Giữ nguyên uncommitted của `prompt_builder.py`.

## Thứ tự thực hiện
- **Phase 1 (A+B):** planner + multi-query retrieve + merge cân bằng + config + tests → pytest.
- **Phase 2 (C):** revise SYSTEM_PROMPT + test chống bịa.
- **Phase 3:** full pytest + smoke `test_chat.py` (Daikin vs Gree, follow-up công nghệ) với API thật.

**Độ phức tạp: MEDIUM** (chủ yếu Phase 1).

---

## Đã làm trước plan này (cùng branch, context-aware retrieval cơ bản)
- `rag/query_rewriter.py` (rewrite_query, fail-open) — sẽ nâng thành planner ở Phase 1.
- `rag/history_store.py` `SessionDocCache` + `chat_engine._doc_cache` + `_merge_context_docs` + `FOLLOWUP_CONTEXT_LIMIT`.
- Query đã viết lại in ra `[debug]` trong `test_chat.py`.
- 31 unit test xanh.
