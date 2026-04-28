# Plan — project_chatbot

> **QUY TẮC**: Luôn đọc file này TRƯỚC KHI bắt đầu bất kỳ công việc nào.
> Sau khi hoàn thành mỗi phase, cập nhật tiến độ vào `.claude/memory.md`.

---

## Phase 0 — Hạ tầng & Sync (làm trước Phase 1)

**Mục tiêu**: Obsidian vault trên máy cá nhân được sync tự động lên Ubuntu server.

### Quyết định: dùng Syncthing
- Obsidian chạy trên máy cá nhân (Windows/Mac), không chạy được trên Ubuntu server headless
- Syncthing sync file `.md` real-time, P2P, miễn phí, không qua cloud
- Server chỉ cần đọc folder vault — không cần Obsidian cài trên server

### Tasks

- [ ] 0.1 Cài Syncthing trên Ubuntu server
  ```bash
  sudo apt install syncthing
  sudo systemctl enable syncthing@$USER
  sudo systemctl start syncthing@$USER
  ```
  - Mở port 8384 (Web UI) chỉ cho localhost hoặc VPN: `http://localhost:8384`
  - Mở port 22000 (sync protocol) nếu máy cá nhân kết nối trực tiếp

- [ ] 0.2 Cài Syncthing trên máy cá nhân
  - Tải tại https://syncthing.net
  - Hoặc dùng plugin **Obsidian Livesync** nếu muốn tích hợp sâu hơn vào Obsidian

- [ ] 0.3 Kết nối 2 thiết bị
  - Lấy Device ID của server → thêm vào Syncthing máy cá nhân
  - Share folder vault (thư mục Obsidian) từ máy cá nhân → server
  - Đặt server là **Receive Only** (chỉ nhận, không ghi ngược lại)

- [ ] 0.4 Xác nhận sync hoạt động
  - Tạo/sửa 1 note trên Obsidian máy cá nhân
  - Kiểm tra file xuất hiện trên server trong vài giây
  - Ghi lại đường dẫn vault trên server → dùng cho `OBSIDIAN_VAULT_PATH` trong `.env`

- [ ] 0.5 Cập nhật `.env` và `CLAUDE.md`
  - Ghi `OBSIDIAN_VAULT_PATH=/path/to/vault` trên server

**Hoàn thành Phase 0 khi**: Sửa note trên Obsidian → file tự động xuất hiện trên server trong <10 giây.

---

## Phase 1 — MVP (1-2 tuần)

**Mục tiêu**: Chạy được pipeline end-to-end, test với câu hỏi mẫu.

### Tasks

- [ ] 1.1 Setup môi trường
  - Tạo virtualenv, cài requirements
  - Tạo `.env` với `GEMINI_API_KEY` và `OBSIDIAN_VAULT_PATH`
  - Viết `config.py`

- [ ] 1.2 Indexer — đọc Obsidian vault
  - `obsidian_loader.py`: đọc tất cả `.md`, parse frontmatter YAML, resolve `[[wiki-links]]`, expand `![[embed]]`, exclude daily notes/templates
  - `embedder.py`: gọi `gemini-embedding-2`, xử lý batch, retry on error
  - `build_index.py`: chạy full index → lưu `data/index.json` (format: `{path, title, content, embedding, metadata}`)

- [ ] 1.3 RAG pipeline
  - `retriever.py`: load `index.json` vào RAM, cosine similarity, return top-k=5
  - `prompt_builder.py`: system prompt + format context từ top-k notes
  - `chat_engine.py`: orchestrate retriever → prompt → Gemini API → response + citations

- [ ] 1.4 API
  - `api/main.py`: FastAPI app, endpoint `POST /chat` nhận `{question: str}` trả `{answer: str, sources: list}`
  - Health check endpoint `GET /health`

- [ ] 1.5 Test MVP
  - Test với 20-30 câu hỏi mẫu
  - Kiểm tra tốc độ (<5s/câu)
  - Kiểm tra chất lượng câu trả lời

**Hoàn thành Phase 1 khi**: API chạy được, trả lời đúng >70% câu hỏi test, tốc độ <5s.

---

## Phase 2 — Production-ready (2-4 tuần)

**Mục tiêu**: Sẵn sàng đưa vào sử dụng thực tế.

### Tasks

- [ ] 2.1 Citations
  - Trả về tên note nguồn + đoạn trích dẫn cụ thể trong response
  - Format: `[Nguồn: Tên note]`

- [ ] 2.2 Logging
  - Lưu mọi Q&A vào `logs/conversations.db` (SQLite)
  - Schema: `id, timestamp, question, answer, sources, latency_ms, user_feedback`
  - Quan trọng: log này là dataset cho Phase 4 fine-tune

- [ ] 2.3 System prompt & Persona
  - Viết system prompt chỉnh chu: tone thương hiệu, cách từ chối khi ngoài scope
  - Guardrails: không bịa giá/khuyến mãi, không trả lời ngoài phạm vi FAQ
  - Từ chối lịch sự khi không tìm được thông tin

- [ ] 2.4 Re-index tự động
  - Script watch vault, re-embed khi note thay đổi (chỉ embed note thay đổi, không rebuild toàn bộ)

- [ ] 2.5 Web widget
  - `widget/index.html`: giao diện chat standalone
  - `widget/widget.js`: script có thể nhúng vào website bất kỳ
  - Hiển thị citations trong UI

- [ ] 2.6 Tích hợp kênh
  - Tích hợp widget vào website công ty

**Hoàn thành Phase 2 khi**: Chatbot live trên website, có logging đầy đủ, guardrails hoạt động.

---

## Phase 3 — Tối ưu (liên tục)

**Mục tiêu**: Cải thiện chất lượng dựa trên dữ liệu thực tế.

### Tasks

- [ ] 3.1 Phân tích log
  - Xác định câu hỏi nào trả sai / không tìm được nguồn
  - Xác định chunks nào hay được retrieve nhưng không hữu ích

- [ ] 3.2 Cải thiện vault
  - Thêm từ đồng nghĩa vào field `keywords` trong frontmatter
  - Chuẩn hóa format note theo template
  - Thêm Q&A thường gặp vào các note liên quan

- [ ] 3.3 Hybrid search (nếu cần)
  - Kết hợp cosine similarity + BM25 keyword search
  - A/B test so sánh kết quả

- [ ] 3.4 Routing LLM (nếu cần)
  - Câu hỏi đơn giản → Gemini Flash
  - Câu hỏi phức tạp, đa bước → Gemini Pro

- [ ] 3.5 Re-ranker (nếu cần)
  - Sắp xếp lại top-k dựa trên độ liên quan sau khi retrieve

**Hoàn thành Phase 3 khi**: Accuracy >85%, latency ổn định <3s.

---

## Phase 4 — Fine-tune (chỉ khi cần)

> **Chỉ bắt đầu khi**: Đã có >1000 cặp Q&A thật từ log, đã qua duyệt, RAG không đáp ứng được yêu cầu về phong cách/tone.

### Tasks

- [ ] 4.1 Chuẩn bị dataset
  - Export log, lọc Q&A chất lượng cao (có feedback tốt hoặc đã được duyệt)
  - Synthetic Q&A chỉ dùng để bổ sung edge cases, luôn có người review

- [ ] 4.2 Fine-tune Gemini
  - Fine-tune để học phong cách trả lời, KHÔNG fine-tune để học kiến thức
  - Kiến thức vẫn nằm trong RAG (vault Obsidian)

- [ ] 4.3 Eval
  - So sánh fine-tuned model vs base model trên test set thật
  - Chỉ deploy nếu cải thiện rõ ràng

---

## Thứ tự ưu tiên

```
Phase 1 (MVP) → Phase 2 (Production) → Phase 3 (Tối ưu) → Phase 4 (Fine-tune)
```

Không nhảy phase. Mỗi phase phải đạt điều kiện hoàn thành mới chuyển sang phase tiếp theo.
