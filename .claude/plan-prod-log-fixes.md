# Plan — Khắc phục theo log production (2026-08-08)

> Nguồn: phân tích 498 record `chatbot_logs.conversations` (MariaDB host) + 485 dòng
> `logs/conversations.jsonl` trên server `172.16.1.222`, khoảng 2026-06-22 → 2026-08-08.
> Đọc `.claude/plan.md` cho roadmap gốc 4 phase. File này là backlog sửa lỗi phát sinh
> từ dữ liệu chạy thật, ưu tiên theo tác động đo được.

---

## Trạng thái thực thi (cập nhật 2026-08-08)

| Nhóm | Trạng thái |
|---|---|
| A.1.5 cảnh báo vault cũ | ✅ code xong |
| A.1.1–A.1.4, A.2, A.3, A.4 | ⛔ **BỊ CHẶN** — cần quyền server `172.16.1.222` (crawler, vault production, `.env`) và 4 câu trả lời của chủ shop ở cuối file. Máy dev chỉ có vault local, **không có** cây mirror `chatbot/` |
| B.1 khớp mã SKU | ✅ code + test |
| B.2 chặn input rác | ✅ code + test |
| B.3.1 đo latency từng chặng | ✅ đã log; **chưa có số liệu** — cần deploy rồi đọc log |
| B.3.2 cổng gọi planner | ✅ đã có sẵn từ trước |
| B.3.3 `MAX_CONTEXT_DOCS`, B.3.4 cold start | ⏳ chờ số liệu B.3.1 |
| C.1, C.2 | ✅ code + test; **chưa đo được hiệu quả** |
| C.3 feedback | ⛔ cần kiểm tra widget trên website thật + migration cột `message_id` |

158 test pass (`python3 -m pytest tests/ -q`). Không đụng `EMBEDDING_MODEL`, không rebuild index.

---

## Số liệu nền (baseline 2026-08-08)

| Chỉ số | Giá trị |
|---|---|
| Record `message` trong MySQL | 498 (333 session, ~1.5 lượt/phiên) |
| Trả lời "chưa có thông tin / không tìm thấy / xin lỗi" | 72 (14.5%) |
| Trả lời đẩy sang hotline | 177 (35.5%) |
| Answer > 1200 ký tự | 105 (21%) |
| Câu hỏi < 15 ký tự (cụt hoặc rác) | 64 (13%) |
| Latency trung bình / max | 6050 ms / 47733 ms |
| Request > 8s | 118 (24%) |
| `user_feedback` khác NULL | **0** — chưa có tín hiệu chất lượng nào |

Phân bố chủ đề câu hỏi: giá 145 · lắp đặt 25 · ship 12 · bảo hành 10 · chi nhánh 9 ·
trả góp 5 · tồn kho 2 · VAT 1.

**Kết luận chẩn đoán**: phần lớn lỗi KHÔNG nằm ở prompt cũng chưa nằm ở RAG — nằm ở
**dữ liệu vault**. Sửa data trước, RAG sau, prompt cuối.

---

## Phase A — Dữ liệu (ưu tiên cao nhất, hầu như không đụng code)

### A.1 Vault đứng yên từ 2026-06-05

**Bằng chứng**: toàn bộ 7612 note gốc có `mtime <= 2026-06-05`;
`data/index.json` (336 MB, 7612 record) build cùng ngày 05/06 16:16.
Sản phẩm khách hỏi mà vault không có (grep = 0 hit):
`Robot Hút Bụi Midea MV15ULTRAAPBK` (id 453, 454), `R-29D2(G/R)VN` (id 435),
`LG ioc12s1` (id 368), `SJ-FXP560V-BK` (id 487).

Bot trả "chưa có thông tin" là **đúng** — không phải retrieval sai.

- [ ] A.1.1 Tìm hiểu vì sao `price_crawler` ngừng đẩy note (chạy tay? cron chết? sync đứt?)
- [ ] A.1.2 Chạy lại crawler, xác nhận note mới xuất hiện trong vault
- [ ] A.1.3 `python -m indexer.build_index --update` — chỉ embed note mới, không rebuild toàn bộ
- [ ] A.1.4 Đặt lịch định kỳ (cron/systemd timer) cho crawler + `--update`
- [x] A.1.5 Cảnh báo vault cũ lúc startup — `api/main.py:_warn_if_vault_stale()`, ngưỡng
      `config.VAULT_STALE_DAYS` (mặc định 7, đổi qua env). Chạy thử trên vault local:
      *"Vault đứng yên 61 ngày (note mới nhất 2026-06-08)"* — xác nhận lại chẩn đoán A.1

### A.2 Vault nhân đôi — chỉ 7612 note thật, không phải 15224

**Bằng chứng**: `chatbot/` là bản mirror y hệt cây gốc. Tập path giống nhau 100%
(`only in chatbot/: 0`, `only in root: 0`). Diff một cặp file: khác đúng 1 dòng
frontmatter `featured: true`.

Index chỉ ăn nhánh gốc (0 path nào bắt đầu bằng `chatbot/`) → **`FEATURED_BOOST = 0.08`
trong `config.py:68` chưa bao giờ kích hoạt**, vì bản được index không có field `featured`.

- [ ] A.2.1 Xác nhận `chatbot/` không phải nguồn được crawler ghi vào (nếu là, đảo ngược quyết định bên dưới)
- [ ] A.2.2 Chuyển `featured: true` sang note gốc, xoá cây `chatbot/`
- [ ] A.2.3 Rebuild index, xác nhận số record có `featured` > 0
- [ ] A.2.4 Test: một truy vấn hãng nổi tiếng phải thấy boost thay đổi thứ hạng

### A.3 Bốn số hotline khác nhau đang cùng phát ra cho khách

**Bằng chứng**: grep `chinh-sach/`:
```
13 × 0983616996      6 × 0918 969 699
 2 × 0983666996      1 × 0983262323
```
`config.py:37` `HOTLINE_NUMBER` mặc định `0983616996`, nhưng
`api/formatting.py:24` chỉ thay **chữ** `"hotline"` bằng số đó. Số thô model chép
nguyên từ note retrieve được thì lọt thẳng ra khách: record id=329 trả `0918 969 699`,
id=464 trả `0983616996` — cùng một bot, hai số.

- [ ] A.3.1 Xác nhận với chủ shop số hotline chính thức duy nhất
- [ ] A.3.2 Xoá/thay mọi số điện thoại thô trong `chinh-sach/`, chỉ để chữ "hotline"
- [ ] A.3.3 Set `HOTLINE_NUMBER` trong `.env` trên server (hiện `.env` **chưa có** biến này — đang chạy bằng default hardcode)
- [ ] A.3.4 Cân nhắc guard trong `formatting.py`: regex bắt số ĐT lạ trong answer → thay bằng số chuẩn

### A.4 Chính sách quá mỏng so với câu khách thật sự hỏi

**Bằng chứng**: `chinh-sach/` chỉ 11 file. grep vault: `Hải Phòng` 0 hit,
`trả góp` 2 hit, `phí vận chuyển` 6 hit, `VAT` 10 hit.
Record id=425 nói thẳng: *"Bên em chưa có thông tin về phí ship cụ thể cho từng tỉnh
thành trong tài liệu ạ"*. Record id=428: hỏi giá vật tư lắp đặt Daikin FTHF25XVMV →
trả được giá máy, không trả được giá lắp.

Đây là chủ đề số 2 và 3 về tần suất (lắp đặt 25, ship 12) mà tài liệu không phủ.

- [ ] A.4.1 Note mới: bảng phí ship theo tỉnh/thành (hoặc quy tắc tính theo khoảng cách)
- [ ] A.4.2 Note mới: bảng giá lắp đặt + vật tư theo nhóm sản phẩm (điều hoà, máy lọc nước, bình nóng lạnh)
- [ ] A.4.3 Bổ sung `Chinh-sach-van-chuyen-lap-dat.md`: định nghĩa rõ "khu vực trong phạm vi hỗ trợ" (id=354 hỏi đúng câu này, không trả được)
- [ ] A.4.4 Note mới: danh sách chi nhánh / khu vực phục vụ (khách hỏi Hải Phòng, Nam Định, Thái Nguyên, Nha Trang)
- [ ] A.4.5 Bổ sung VAT/xuất hoá đơn vào `Hinh-thuc-thanh-toan.md` (id=481)
- [ ] A.4.6 Mở rộng `Chinh-sach-tra-gop.md`: thẻ tín dụng, Visa (id=414, 455)
- [ ] A.4.7 Thêm `keywords` tiếng lóng/sai chính tả vào frontmatter các note chính sách
      (khách gõ "hả phòng", "ãu", "ja", "kh", "dc")

---

## Phase B — RAG (sau khi data sạch)

### B.1 Truy vấn theo mã SKU thất bại

**Bằng chứng**: `u9bkh khác gì xu9bkh` (id 394, 404), `yz9akh khác gì xz9bkh` (id 288),
`SJ-FXP560V-BK` (id 487), `Model: R-29D2(G/R)VN` (id 435), `014040` (id 479).
Embedding rất yếu với chuỗi mã. Cosine trả về sản phẩm cùng danh mục nhưng sai mã.

- [x] B.1.1 `build_code_index()` dựng map { mã → record } lúc load index; record khớp mã được
      nạp thẳng vào pool ứng viên dù cosine nằm ngoài top-100
- [x] B.1.2 Nhận diện mã dùng lại `_model_code_tokens` (≥4 ký tự, có cả chữ lẫn số) →
      `_code_match_boost = config.CODE_MATCH_BOOST (0.5)`, lớn hơn tổng keyword+policy+featured
- [x] B.1.3 `Retriever.unmatched_model_codes()` → `chat_engine` cắt context còn
      `config.FALLBACK_MAX_DOCS = 2` và `build_prompt(..., missing_codes)` bắt model nói thẳng
      "chưa có mã này"
- [x] B.1.4 `tests/test_retriever_sku.py` (11 test) + `test_missing_code_caps_context_docs`
      trong `tests/test_fixes.py`

### B.2 Chặn input rác trước khi gọi API

**Bằng chứng**: 64 câu < 15 ký tự. Trong 120 câu gần nhất, ~30 câu là gõ phím ngẫu nhiên
(`Ehfubrfuehfbrfuehf`, `Vhrfurhfurvfurhufrhfuhrufhrfu`, `Ĥp00`, `3 nn`, `O`).
Mỗi câu vẫn tốn 1 lần embedding + 1 lần gọi LLM. Record id=310 (`Beheuysydgh3vssgyggsgsy`)
mất **29 giây**.

- [x] B.2.1 `rag/input_guard.py:is_gibberish()` — chuỗi chữ cái liền ≥11 ký tự có tỉ lệ nguyên
      âm <0.34 ("y" không tính là nguyên âm) → rác; cộng thêm ca chỉ dấu câu / một chữ cái đơn
- [x] B.2.2 Trả `GIBBERISH_REPLY` tĩnh; không embed, không retrieve, không gọi LLM, không ghi
      response cache, KHÔNG ghi history (rác vào history sẽ đầu độc planner lượt sau)
- [x] B.2.3 Vẫn ghi `type="message"` qua `_gibberish_response()`
- [x] B.2.4 `tests/test_input_guard.py` — 7 chuỗi rác thật trong log bị chặn; 13 câu thật
      (kể cả "5.", "014040", "SJ-FXP560V-BK", "u9bkh khác gì xu9bkh") KHÔNG bị chặn

### B.3 Latency

**Bằng chứng**: trung bình 6.0s (mục tiêu CLAUDE.md < 5s), 118 request > 8s.
Các ca chậm nhất (29–48s) tập trung ở id 197–330 (tháng 6). Xu hướng gần đây đã tốt hơn
(05/08: avg 6.9s, 07/08: avg 5.5s) nhưng vẫn 2–4 request/ngày > 8s.

- [x] B.3.1 Log 2 dòng INFO mỗi lượt: `retrieval embed=…ms rank=…ms` (trong `Retriever.search`)
      và `stages plan=…ms retrieve=…ms llm=…ms nq=… ndocs=…` (trong `chat_engine.answer`)
- [x] B.3.2 ĐÃ có sẵn từ trước — `plan_search_queries` chỉ gọi LLM khi có history hoặc câu
      lượt đầu có ý so sánh (`_looks_like_comparison`); câu thường lượt đầu không tốn round-trip.
      Cần đo lại bằng log B.3.1 rồi mới kết luận
- [ ] B.3.3 Xem lại `MAX_CONTEXT_DOCS = 8` — context dài kéo dài thời gian sinh
- [ ] B.3.4 Index 336 MB load in-memory: kiểm tra thời gian cold start sau restart

---

## Phase C — Prompt (tác động nhỏ nhất, làm cuối)

### C.1 Không tìm thấy → đổ sản phẩm không liên quan

**Bằng chứng**: id=496, khách gõ chuỗi vô nghĩa
(`Hoàng khåc Dân AG pro max 💯📜 P10 ...`), bot trả **1275 ký tự** liệt kê quạt công
nghiệp Hatari + máy lọc nước Karofi + bình nóng lạnh Ariston — nối theo "AG", "pro max".
id=454: hỏi robot Midea không có, bot đổ 2 robot Hitachi, 1552 ký tự.

- [x] C.1.1 Rule 7 trong `SYSTEM_PROMPT`: không khớp → nói ngắn, HỎI LẠI, chỉ gợi ý CÙNG DANH MỤC
- [x] C.1.2 Ràng buộc ở TẦNG CODE (không chỉ prompt): `config.FALLBACK_MAX_DOCS = 2` cắt số
      tài liệu vào prompt khi khách hỏi mã không có
- [x] C.1.3 4 test mới trong `tests/test_prompt.py`

### C.2 Trả lời quá dài

**Bằng chứng**: trung bình 717 ký tự, 105 answer > 1200 ký tự.
Phản hồi thật của khách, record id=410: *"Hỏi 2 mẫu mà trả lời lắm thế"*.

- [x] C.2.1 Mục "ĐỘ DÀI CÂU TRẢ LỜI" trong `SYSTEM_PROMPT`: mặc định <~600 ký tự, chỉ trả dài
      khi khách hỏi đúng MỘT sản phẩm cụ thể
- [x] C.2.2 Liệt kê nhiều sản phẩm → chỉ tên + giá + link, bỏ thông số kỹ thuật
- [ ] C.2.3 **Chưa đo được hiệu quả** — cần so độ dài trung bình answer trước/sau khi deploy
      (baseline: 717 ký tự, 105 answer > 1200)

### C.3 Không có tín hiệu chất lượng

**Bằng chứng**: `user_feedback` NULL trên cả 498 row. Endpoint `/feedback` tồn tại,
`log_feedback` ghi `type="feedback"` vào JSONL — nhưng JSONL production **0 record feedback**,
và `_read_pending` cố tình lọc bỏ nên MySQL không bao giờ nhận (xem CLAUDE.md).

Không có feedback thì mọi thay đổi prompt ở Phase C đều là đoán mò.

- [ ] C.3.1 Kiểm tra widget trên website thật có render nút thumbs up/down không
- [ ] C.3.2 Nếu có mà không ai bấm → làm nổi bật hơn / hỏi sau N lượt
- [ ] C.3.3 Thêm cột `message_id` + migration để feedback map được sang `conversations` (điều kiện tiên quyết đã ghi trong CLAUDE.md)
- [ ] C.3.4 Chỉ bắt đầu tinh chỉnh prompt sau khi có ≥50 feedback thật

---

## Thứ tự thực thi đề xuất

```
A.1 (crawler + index)  ──┐
A.3 (hotline)          ──┼── làm song song, không đụng code pipeline
A.4 (note chính sách)  ──┘
        ↓
A.2 (xoá mirror, bật featured boost)   ← cần rebuild index, làm sau A.1
        ↓
B.2 (chặn rác)  →  B.1 (SKU match)  →  B.3 (latency)
        ↓
C.3 (bật feedback)  →  đợi dữ liệu  →  C.1, C.2
```

**Lý do**: Phase A sửa được phần lớn ca "chưa có thông tin" mà không cần viết dòng code
pipeline nào. Chỉnh prompt trước khi vá data chỉ dạy bot nói khéo hơn về thứ nó không biết.

---

## Rủi ro

| Rủi ro | Mức | Ghi chú |
|---|---|---|
| Xoá cây `chatbot/` mà nó mới là nguồn crawler ghi vào | CAO | Bắt buộc làm A.2.1 trước, backup trước khi xoá |
| Rebuild index sai model → cosine lệch không gian | CAO | `EMBEDDING_MODEL` phải giữ `gemini-embedding-2` (bất biến trong CLAUDE.md) |
| Guard input rác chặn nhầm câu follow-up hợp lệ | TRUNG BÌNH | Câu cụt như "Tôi ở HN", "18.000 BTU", "5." là hợp lệ — test kỹ ở B.2.4 |
| Thay số ĐT thô bằng regex bắt nhầm mã sản phẩm chứa số | THẤP | A.3.4 là tuỳ chọn, cân nhắc bỏ |
| Chi phí embed lại toàn bộ vault | THẤP | Dùng `--update`, không rebuild |

---

## Việc chưa quyết, cần hỏi chủ shop

1. Số hotline chính thức duy nhất là số nào? (A.3.1)
2. Có bảng phí ship theo tỉnh không, hay luôn "liên hệ để báo giá"? (A.4.1)
3. Giá lắp đặt/vật tư có công bố được không, hay là thông tin chỉ nhân viên báo? (A.4.2)
4. Danh sách chi nhánh / phạm vi phục vụ thực tế? (A.4.4)
