# Memory — Tiến độ dự án project_chatbot

> File này lưu trạng thái tiến độ. Cập nhật sau mỗi phase hoặc session làm việc.
> Luôn đọc `.claude/plan.md` để biết task cụ thể cần làm.

---

## Trạng thái hiện tại

**Phase đang làm**: Phase 3 — Tối ưu
**Bắt đầu**: 2026-04-21
**Cập nhật lần cuối**: 2026-05-24

---

## Đã hoàn thành

### Setup & Planning (2026-04-21)
- [x] Thảo luận kiến trúc, chọn Phương án C (embedding siêu nhẹ, file JSON)
- [x] Xác định tech stack: Python + FastAPI + Gemini API + Web widget
- [x] Xác định deployment: Local trên máy công ty
- [x] Tạo `CLAUDE.md` với cấu trúc dự án
- [x] Tạo `.claude/plan.md` với roadmap 4 phases
- [x] Tạo `.claude/memory.md` (file này)
- [x] Tạo cấu trúc thư mục dự án

### Phase 2 — Production-ready ✅ (branch: feat/phase2-production, 2026-05-24)
- [x] 2.1 Citations — system prompt + `sources` field đã có từ Phase 1
- [x] 2.2 Logging MySQL — kiến trúc 2 tầng: chatbot → JSONL local → auto-sync → MySQL
  - `logs/conversation_store.py`: ghi JSONL, không cần MySQL credentials
  - `logs/sync_to_mysql.py`: sync worker có MySQL credentials
  - `logs/auto_sync.py`: debounce timer per session (180s idle → trigger sync)
  - Session tracking: `session_id` UUID theo từng cuộc trò chuyện
- [x] 2.3 System prompt & Persona — refine tone thương hiệu Điện Máy Thiên Phú
- [x] 2.4 Re-index tự động — `indexer/watcher.py` watchdog theo dõi vault, chỉ re-embed note thay đổi

---

## Đang làm

### Phase 3 — Tối ưu
- [ ] 3.1 Phân tích log
- [ ] 3.2 Cải thiện vault
- [ ] 3.3 Hybrid search (nếu cần)
- [ ] 3.4 Routing LLM (nếu cần)
- [ ] 3.5 Re-ranker (nếu cần)

### Phase 1 — MVP
- [x] 1.1 Setup môi trường: `requirements.txt`, `.env.example`, `config.py`
- [x] 1.2 Indexer: `obsidian_loader.py`, `embedder.py`, `build_index.py`
- [x] 1.3 RAG pipeline: `retriever.py`, `prompt_builder.py`, `chat_engine.py`
- [x] 1.4 API: `api/main.py` (POST /chat, GET /health, GET /widget)
- [x] 1.5 Chạy evaluation 30 câu hỏi → kết quả 0/30 PASS (xem `.claude/plan-fix-chatbot.md`)

### Phase 1.5 — Sửa lỗi sau Evaluation (xem `.claude/plan-fix-chatbot.md`)
- [x] Fix 1: Thay GEval bằng custom Gemini evaluator (bypass GEval bug non-OpenAI), thêm retry vào bot — Pass rate 70% ✅ (2026-05-21)
- [x] Fix 2: Thêm 5 notes vào vault `D:\chatbot\` (dữ liệu từ dienmaythienphu.vn 2026-05-20)
  - [x] `Dieu-hoa-tong-quan.md`
  - [x] `Chinh-sach-van-chuyen-lap-dat.md`
  - [x] `Chinh-sach-tra-gop.md`
  - [x] `Pham-vi-kinh-doanh.md`
  - [x] `May-giat-tu-van.md`
  - [x] Chạy lại `build_index.py` → 7611 docs embedded, index.json saved (2026-05-21)
- [x] Fix 3: Thêm keywords vào `Chinh-sach-bao-hanh.md` + xác nhận 2 notes kia đã có đủ keywords (2026-05-21)
- [x] Fix 4: Sửa system prompt `rag/prompt_builder.py` — thêm rule phủ định rõ ràng (2026-05-21)
- [x] Fix 5: Retrieval improvement — policy boost + metadata keywords + always include policy notes in candidate pool (2026-05-22)
- [x] Fix 6: Tăng content limit từ 1500 → 3000 chars trong prompt_builder.py (2026-05-22)
- [x] Fix 7: Tạo `Chinh-sach-gia.md` (mặc cả, khuyến mãi) + update `Dieu-hoa-tong-quan.md` (tặng kèm) (2026-05-22)
- [x] Chạy lại eval → **Pass rate: 96.7% (29/30)** ✅ (2026-05-22)
  - Câu fail duy nhất: [7] "Tivi 55 inch giá bao nhiêu?" (correctness=0.4) — edge case giá sản phẩm cụ thể

---

## Chưa bắt đầu

- Phase 4 — Fine-tune

---

## Ghi chú / Quyết định trong quá trình làm

- **2026-04-21**: Deployment là Ubuntu server headless → Obsidian không chạy được trực tiếp trên server. Quyết định dùng **Syncthing** để sync vault từ máy cá nhân lên server real-time. Server set Receive Only, chỉ đọc file `.md`. Thêm Phase 0 vào plan trước Phase 1.
- **2026-05-24**: Logging dùng kiến trúc 2 tầng thay vì ghi thẳng MySQL. Chatbot chỉ ghi file JSONL local (không cần DB credentials). Background debounce timer (180s/session) tự động sync lên MySQL. MySQL chạy port 3307 (không phải 3306 mặc định).

---

## Hướng dẫn cập nhật file này

Sau mỗi phase hoặc session làm việc, cập nhật:
1. **Trạng thái hiện tại**: phase đang làm, ngày cập nhật
2. **Đã hoàn thành**: tick [x] vào task xong, thêm ngày hoàn thành
3. **Đang làm**: danh sách task của phase hiện tại
4. **Ghi chú**: ghi lại quyết định quan trọng, vấn đề gặp phải
