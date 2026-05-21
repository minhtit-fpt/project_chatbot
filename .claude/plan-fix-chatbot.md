# Plan — Sửa lỗi Chatbot sau Evaluation (Phase 1.5)

> **Bối cảnh**: Sau khi chạy DeepEval evaluation 30 câu hỏi (Google Sheets gid=679480547),
> kết quả 0/30 PASS. Phân tích phát hiện 4 nhóm vấn đề.
>
> **Mục tiêu**: Tăng pass rate lên >70% trên bộ 30 câu test.
> **Ngày tạo**: 2026-05-20

---

## Fix 1 — Sửa DeepEval evaluation metric

**Vấn đề**: `answer_relevancy` toàn cho điểm 0.02–0.07 kể cả khi bot trả lời đúng → 30/30 FAIL giả.
**Nguyên nhân nghi ngờ**: GEval với Gemini tính điểm sai (chia theo số steps → ra số cực nhỏ).

- [x] 1.a Bỏ qua verbose debug — code đã đủ rõ để phân tích trực tiếp
- [x] 1.b Chuyển từ `criteria` sang `evaluation_steps` (cách DeepEval recommend cho non-OpenAI models) — 2026-05-21
- [x] 1.c Đổi tên cột sheet `answer_relevancy` → `correctness` cho đúng bản chất — 2026-05-21
- [ ] 1.d Chạy lại toàn bộ 30 câu với `--force`, xác nhận score hợp lý (≥ 0.5 cho câu đúng)

**File cần sửa**: `eval/run_deepeval.py`

---

## Fix 2 — Thêm notes vào Obsidian Vault ✅ XONG

**Vấn đề**: Bot nói "Tôi chưa có thông tin" cho 7+ chủ đề vì vault thiếu notes.
**Dữ liệu lấy từ**: dienmaythienphu.vn ngày 2026-05-20.

- [x] 2.a Tạo `Dieu-hoa-tong-quan.md` — fix câu #2 (điều hòa tổng quan)
- [x] 2.b Tạo `Chinh-sach-van-chuyen-lap-dat.md` — fix câu #17–22 (giao hàng, lắp đặt, giờ giao)
- [x] 2.c Tạo `Chinh-sach-tra-gop.md` — fix câu #23, #26 (trả góp, điều kiện)
- [x] 2.d Tạo `Pham-vi-kinh-doanh.md` — fix câu #6, #11, #22 (ô tô điện, hàng miễn phí, giao nước ngoài)
- [x] 2.e Tạo `May-giat-tu-van.md` — fix câu #4 (máy giặt tiết kiệm điện nhất)
- [x] 2.f Chạy lại `python -m indexer.build_index` → 7611 docs embedded, saved data/index.json — 2026-05-21

---

## Fix 3 — Cải thiện keywords trong notes hiện có (retrieval nhầm)

**Vấn đề**: Câu #11, #16, #21 bot retrieve sai note → trả lời lạc đề.

| # | Câu hỏi | Bot trả sai | Fix |
|---|---|---|---|
| 11 | "Bán hàng miễn phí không?" | Phương thức mua hàng | Thêm keyword `mien-phi, tang-khong` vào `Pham-vi-kinh-doanh.md` |
| 16 | "Đập vỡ màn hình có bảo hành?" | Liệt kê sản phẩm tivi | Thêm keyword `vo-man-hinh, roi-vo, va-dap` vào `Chinh-sach-bao-hanh.md` |
| 21 | "Giao hàng buổi tối được không?" | Phương thức mua hàng | Thêm keyword `buoi-toi, gio-giao, khung-gio` vào `Chinh-sach-van-chuyen-lap-dat.md` |

- [x] 3.a Thêm frontmatter + keywords vào `D:\chatbot\Chinh-sach-bao-hanh.md` (vo-man-hinh, roi-vo, va-dap...) — 2026-05-21
- [x] 3.b Đã xác nhận `Chinh-sach-van-chuyen-lap-dat.md` có "giao hàng buổi tối", "giao hàng ban đêm" ✅
- [x] 3.c Đã xác nhận `Pham-vi-kinh-doanh.md` có "hàng miễn phí", "cho không hàng", "tặng không" ✅

**File cần sửa**: `D:\chatbot\Chinh-sach-bao-hanh.md` (thêm frontmatter keywords)

---

## Fix 4 — Cải thiện System Prompt (phủ định đúng)

**Vấn đề**: Bot nói "Tôi chưa có thông tin" thay vì phủ định rõ khi tài liệu đã nêu shop không làm gì.
**Câu bị ảnh hưởng**: #6 (ô tô điện), #22 (giao nước ngoài).

- [x] 4.a Thêm rule vào `SYSTEM_PROMPT` trong `rag/prompt_builder.py` — 2026-05-21:
  ```
  Nếu tài liệu cho thấy shop KHÔNG kinh doanh mặt hàng hoặc KHÔNG cung cấp dịch vụ đó,
  hãy trả lời thẳng: "Xin lỗi, cửa hàng không [bán/cung cấp] X."
  Không nói "Tôi chưa có thông tin" khi tài liệu đã nêu rõ phạm vi kinh doanh.
  ```

**File cần sửa**: `rag/prompt_builder.py`

---

## Thứ tự thực hiện

```
Fix 1 (DeepEval metric) → chạy test thử 3 câu
        ↓
Fix 2.f (re-index) + Fix 3 (keywords) — song song
        ↓
Fix 4 (system prompt)
        ↓
Chạy lại evaluation --force toàn bộ 30 câu
        ↓
Xác nhận pass rate ≥ 70%
```

**Hoàn thành khi**: Pass rate ≥ 70% trên 30 câu, GEval score ≥ 0.5 cho câu trả lời đúng.
