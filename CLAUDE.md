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
| Embedding | Gemini `gemini-embedding-2` (xem `config.EMBEDDING_MODEL`) |
| LLM | Gemini 2.5 Flash (production) / Gemini 2.5 Pro (phức tạp) |
| Vector store | file `index.json` (in-memory cosine similarity) |
| Data source | Obsidian Vault (>1000 notes, local) |
| Deployment | Local — máy công ty |
| Logging | MySQL (`chatbot_logs.conversations`, port 3307) |

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
│   ├── obsidian_loader.py      # Đọc .md, parse frontmatter, xử lý [[wiki-links]]; to_vault_relative()
│   ├── embedder.py             # Gọi Gemini embedding API
│   ├── build_index.py          # Script build/update index.json (--update, --refresh-meta)
│   └── watcher.py              # Watchdog theo dõi vault, re-embed note thay đổi (path tương đối)
├── rag/
│   ├── __init__.py
│   ├── retriever.py            # Cosine similarity in-memory, top-k + keyword/policy/featured boost
│   ├── prompt_builder.py       # System prompt + context builder
│   ├── retry.py                # Exponential backoff cho Gemini API (is_retryable, call_with_retry)
│   └── chat_engine.py          # Orchestrator RAG pipeline (async, TTL cache, model chain, fallback)
├── api/
│   ├── __init__.py
│   ├── main.py                 # FastAPI app: /chat, /feedback, /session, /health (lifespan)
│   └── formatting.py           # format_answer_lines: tách answer thành mảng từng dòng cho FE
├── tests/
│   └── test_fixes.py           # Unit test (pytest, mock — không gọi API thật)
├── data/
│   └── index.json              # Vector index (gitignore)
└── logs/
    ├── __init__.py
    ├── conversation_store.py   # Ghi Q&A vào JSONL local (không cần MySQL); get_write_lock()
    ├── auto_sync.py            # Debounce timer per session → trigger sync
    ├── sync_to_mysql.py        # Sync JSONL → MySQL (chỉ module này cần DB credentials)
    ├── mysql_logger.py         # MySQL connection helper (dùng bởi sync_to_mysql)
    └── conversations.jsonl     # Buffer local Q&A (gitignore)
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

### Logging 2 tầng (Phase 2)
- Chatbot ghi Q&A vào `logs/conversations.jsonl` (local, không cần MySQL credentials)
- `auto_sync.py` debounce 180s per `session_id` → khi session idle → gọi `sync_to_mysql.py`
- Chỉ `sync_to_mysql.py` cần MySQL credentials → giảm attack surface
- MySQL chạy port **3307** (không phải 3306), database `chatbot_logs`
- Mỗi cuộc trò chuyện có `session_id` UUID riêng — client giữ và gửi kèm mỗi request

### Bất biến: path-key của record index phải TƯƠNG ĐỐI so với vault root
- `build_index.py` (qua `load_vault`) và `watcher.py` (qua `load_single_file`) đều phải
  sinh `path` **tương đối** (vd `tivi/Samsung-X.md`), dùng làm khóa định danh record.
- Nếu một bên dùng path tuyệt đối → watcher tạo **record trùng** và phá `_policy_boost`
  (hàm này kiểm tra path KHÔNG chứa `/` hay `\`). Đây là bug đã sửa — dùng `to_vault_relative()`.

### Bất biến: model embedding của query phải KHỚP model đã build index
- `config.EMBEDDING_MODEL` hiện là `gemini-embedding-2`. Đổi model → phải **rebuild index**
  (`python -m indexer.build_index`), nếu không query vector và document vector lệch không gian → cosine sai.

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
