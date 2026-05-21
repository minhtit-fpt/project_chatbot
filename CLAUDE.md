# CLAUDE.md — project_chatbot

> File này chỉ lưu cấu trúc dự án và những quyết định quan trọng.
> Để biết cần làm gì, luôn đọc `.claude/plan.md` trước.
> Để biết tiến độ hiện tại, đọc `.claude/memory.md`.

---

## Rules

1. Luôn đọc `.claude/plan.md` trước khi bắt đầu làm việc.
2. Sau mỗi phase hoàn thành, cập nhật tiến độ vào `.claude/memory.md`.
3. **Không bao giờ commit thẳng vào `main`** — mọi thay đổi phải tạo branch riêng, sau đó mở PR để merge.

---

## Tổng quan dự án

**Mục tiêu**: Chatbot trả lời câu hỏi khách hàng (FAQ bán hàng) dựa trên dữ liệu từ Obsidian vault.

**Kiến trúc**: Phương án C — Embedding siêu nhẹ (file JSON, không vector DB)

```
Obsidian Vault (.md)
      ↓
Embedding (Gemini text-embedding-004) → index.json (lưu local)
      ↓
User hỏi → Embed câu hỏi → Cosine similarity in-memory
      ↓
Top 5 notes → Gemini 2.5 Flash → Trả lời + citations
```

---

## Tech Stack

| Thành phần | Công nghệ |
|---|---|
| Language | Python |
| Backend | FastAPI |
| Embedding | Gemini text-embedding-004 |
| LLM | Gemini 2.5 Flash (production) / Gemini 2.5 Pro (phức tạp) |
| Vector store | file `index.json` (in-memory cosine similarity) |
| Data source | Obsidian Vault (>1000 notes, local) |
| Deployment | Local — máy công ty |
| Logging | SQLite (`logs/conversations.db`) |

---

## Cấu trúc dự án

```
project_chatbot/
├── CLAUDE.md                   # File này
├── .claude/
│   ├── plan.md                 # Roadmap 4 phases — đọc trước khi làm
│   └── memory.md               # Tiến độ hiện tại — cập nhật sau mỗi phase
├── .env                        # GEMINI_API_KEY, OBSIDIAN_VAULT_PATH
├── requirements.txt
├── config.py                   # Cấu hình tập trung
├── indexer/
│   ├── __init__.py
│   ├── obsidian_loader.py      # Đọc .md, parse frontmatter, xử lý [[wiki-links]]
│   ├── embedder.py             # Gọi Gemini embedding API
│   └── build_index.py          # Script build/update index.json
├── rag/
│   ├── __init__.py
│   ├── retriever.py            # Cosine similarity in-memory, top-k
│   ├── prompt_builder.py       # System prompt + context builder
│   ├── retry.py                # Exponential backoff + jitter cho Gemini API
│   └── chat_engine.py          # Orchestrator RAG pipeline (async, TTL cache)
├── api/
│   ├── __init__.py
│   └── main.py                 # FastAPI app, endpoint /chat
├── data/
│   └── index.json              # Vector index (gitignore)
└── logs/
    └── conversations.db        # SQLite log Q&A (gitignore)
```

---

## Quyết định kiến trúc quan trọng

### Tại sao không dùng ChromaDB / vector DB?
- Vault 1000 notes → file JSON ~30-50MB, load in-memory, search vài chục ms
- Không cần infrastructure phức tạp
- Dễ deploy local, không cần service ngoài

### Tại sao không dùng long-context (nhồi cả vault)?
- 1000 notes × 500 từ ≈ 650K tokens → ~$0.81/câu hỏi, quá đắt
- Latency 15-30s, khách hàng không chấp nhận

### Tại sao chọn Gemini 2.5 Flash cho production?
- Mục tiêu tốc độ <5s/câu hỏi
- Flash: nhanh, rẻ, đủ thông minh cho FAQ
- Pro: chỉ dùng routing tự động khi câu hỏi phức tạp

### Reliability & Performance (branch feat/reliability-and-performance)
- `answer()` là async — không block FastAPI event loop, dùng `asyncio.to_thread` cho sync SDK calls
- `rag/retry.py`: exponential backoff + full jitter, retry tối đa 5 lần cho 503/429
- Fallback tự động sang `gemini-2.0-flash` nếu model chính fail hết retry
- TTL cache in-memory (256 entries, 5 phút) — câu hỏi giống nhau trả về ngay, latency ~0ms

### Fine-tune sẽ làm ở Phase 4 (chưa cần ngay)
- Phase 4 chỉ kích hoạt khi đã có đủ log dữ liệu thật từ khách hàng
- Dùng dữ liệu log (đã duyệt), không dùng synthetic Q&A làm dataset chính

---

## Template chuẩn cho Obsidian notes (FAQ)

```markdown
---
title: Tên sản phẩm/chủ đề
tags: [san-pham, danh-muc-A]
keywords: [từ khoá 1, từ đồng nghĩa, tên gọi khác]
category: san-pham | chinh-sach | huong-dan | khuyen-mai
last_updated: 2026-04-21
---

# Tên ngắn gọn

## Mô tả
...

## Câu hỏi thường gặp
- Q: ...
  A: ...

## Liên quan
- [[Note khác]]
```

> Field `keywords` là quan trọng nhất — liệt kê các cách khách hay hỏi (từ đồng nghĩa, tiếng lóng, lỗi chính tả phổ biến).

---

## Lưu ý đặc thù Obsidian

- `[[wiki-links]]`: parse và resolve thành metadata link
- Frontmatter YAML: dùng làm metadata filter
- `![[embed]]`: expand nội dung trước khi embedding
- Daily notes / Templates: exclude khỏi index
- Notes có nhiều backlinks = quan trọng hơn → ưu tiên trong ranking
