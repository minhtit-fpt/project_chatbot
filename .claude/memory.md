# Memory — Tiến độ dự án project_chatbot

> File này lưu trạng thái tiến độ. Cập nhật sau mỗi phase hoặc session làm việc.
> Luôn đọc `.claude/plan.md` để biết task cụ thể cần làm.

---

## Trạng thái hiện tại

**Phase đang làm**: Phase 1 — MVP (tasks 1.1–1.4 đã xong, còn 1.5 test)
**Bắt đầu**: 2026-04-21
**Cập nhật lần cuối**: 2026-04-23

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

---

## Đang làm

### Phase 1 — MVP
- [x] 1.1 Setup môi trường: `requirements.txt`, `.env.example`, `config.py`
- [x] 1.2 Indexer: `obsidian_loader.py`, `embedder.py`, `build_index.py`
- [x] 1.3 RAG pipeline: `retriever.py`, `prompt_builder.py`, `chat_engine.py`
- [x] 1.4 API: `api/main.py` (POST /chat, GET /health, GET /widget)
- [ ] 1.5 Test MVP với 20-30 câu hỏi mẫu

---

## Chưa bắt đầu

- Phase 1 — MVP
- Phase 2 — Production-ready
- Phase 3 — Tối ưu
- Phase 4 — Fine-tune

---

## Ghi chú / Quyết định trong quá trình làm

- **2026-04-21**: Deployment là Ubuntu server headless → Obsidian không chạy được trực tiếp trên server. Quyết định dùng **Syncthing** để sync vault từ máy cá nhân lên server real-time. Server set Receive Only, chỉ đọc file `.md`. Thêm Phase 0 vào plan trước Phase 1.

---

## Hướng dẫn cập nhật file này

Sau mỗi phase hoặc session làm việc, cập nhật:
1. **Trạng thái hiện tại**: phase đang làm, ngày cập nhật
2. **Đã hoàn thành**: tick [x] vào task xong, thêm ngày hoàn thành
3. **Đang làm**: danh sách task của phase hiện tại
4. **Ghi chú**: ghi lại quyết định quan trọng, vấn đề gặp phải
