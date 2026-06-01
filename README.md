# FAQ Chatbot

Chatbot trả lời câu hỏi khách hàng (FAQ bán hàng) dựa trên dữ liệu từ Obsidian vault, sử dụng RAG (Retrieval-Augmented Generation) với Gemini.

## Kiến trúc

```
Obsidian Vault (.md)
      ↓
Embedding (Gemini text-embedding-004) → index.json (lưu local)
      ↓
User hỏi → Embed câu hỏi → Cosine similarity in-memory
      ↓
Top 5 notes → Gemini 2.5 Flash → Trả lời + citations
      ↓
Ghi log JSONL local → debounce 180s → sync MySQL
```

**Điểm đặc trưng**: Không dùng vector DB (ChromaDB, Pinecone...). Toàn bộ embedding lưu trong `index.json`, search in-memory — đủ nhanh cho vault ~1000 notes, không cần infrastructure phức tạp.

## Tech Stack

| Thành phần | Công nghệ |
|---|---|
| Language | Python 3.11+ |
| Backend | FastAPI |
| Embedding | Gemini text-embedding-004 |
| LLM | Gemini 2.5 Flash / 2.5 Pro |
| Vector store | `index.json` (in-memory cosine similarity) |
| Data source | Obsidian Vault (local) |
| Logging | MySQL port 3307, database `chatbot_logs` |

## Cấu trúc dự án

```
project_chatbot/
├── config.py                   # Cấu hình tập trung (đọc từ .env)
├── indexer/
│   ├── obsidian_loader.py      # Đọc .md, parse frontmatter, [[wiki-links]]
│   ├── embedder.py             # Gọi Gemini embedding API
│   └── build_index.py          # Script build/rebuild index.json
├── rag/
│   ├── retriever.py            # Cosine similarity, top-k
│   ├── prompt_builder.py       # System prompt + context builder
│   └── chat_engine.py          # RAG pipeline orchestrator
├── api/
│   └── main.py                 # FastAPI app — POST /chat, GET /health
├── logs/
│   ├── conversation_store.py   # Ghi Q&A vào JSONL local
│   ├── auto_sync.py            # Debounce timer per session_id
│   ├── sync_to_mysql.py        # Sync JSONL → MySQL
│   └── mysql_logger.py         # MySQL connection helper
├── data/
│   └── index.json              # Vector index (gitignore)
└── .env                        # Secrets (gitignore)
```

## Cài đặt

Có 2 cách cài đặt: **Docker** (khuyến nghị cho production) hoặc **thủ công** (phát triển local).

---

### Cách 1 — Docker (khuyến nghị)

Yêu cầu: [Docker Desktop](https://www.docker.com/products/docker-desktop/) đã cài và đang chạy.

#### 1. Clone và tạo file `.env`

```bash
git clone <repo-url>
cd project_chatbot
cp .env.example .env
```

Điền các giá trị vào `.env`:

```env
GEMINI_API_KEY=your_gemini_api_key_here
OBSIDIAN_VAULT_PATH=C:\path\to\your\obsidian\vault   # đường dẫn trên máy host

MYSQL_USER=chatbot
MYSQL_PASSWORD=your_password_here
MYSQL_DATABASE=chatbot_logs
MYSQL_ROOT_PASSWORD=your_root_password_here
```

> - `OBSIDIAN_VAULT_PATH` là đường dẫn trên máy host — Docker tự mount vào container.
> - `MYSQL_HOST` và `MYSQL_PORT` **không cần điền** — Docker override tự động.
> - Lấy Gemini API key tại [Google AI Studio](https://aistudio.google.com/apikey).

#### 2. Build và khởi động

```bash
docker compose up -d
```

Lần đầu sẽ mất vài phút để pull image và build. Các lần sau khởi động gần như tức thì.

#### 3. Build index lần đầu

```bash
docker compose exec -e PYTHONPATH=/app chatbot python indexer/build_index.py
```

> Chỉ cần chạy lần đầu. Sau đó dùng watcher (xem phần [Rebuild index tự động](#rebuild-index-tự-động)).

#### 4. Kiểm tra

```bash
docker compose ps          # kiểm tra trạng thái services
docker compose logs -f     # xem logs real-time
```

Server sẵn sàng tại `http://localhost:8000`.

#### Các lệnh Docker thường dùng

```bash
docker compose stop                               # dừng (giữ data)
docker compose down                               # dừng và xoá containers
docker compose down -v                            # dừng và xoá cả volumes (reset DB)
docker compose restart chatbot                    # restart chỉ app
docker compose exec chatbot python -m logs.sync_to_mysql --dry-run
```

---

### Cách 2 — Cài đặt thủ công

#### 1. Clone và tạo môi trường

```bash
git clone <repo-url>
cd project_chatbot
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # Linux/Mac
pip install -r requirements.txt
```

#### 2. Tạo file `.env`

```bash
cp .env.example .env
```

Điền các giá trị vào `.env`:

```env
GEMINI_API_KEY=your_gemini_api_key_here
OBSIDIAN_VAULT_PATH=C:\path\to\your\vault

# MySQL logging (tuỳ chọn — bỏ trống nếu chưa có DB)
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3307
MYSQL_USER=chatbot
MYSQL_PASSWORD=your_password_here
MYSQL_DATABASE=chatbot_logs
```

> Lấy Gemini API key tại [Google AI Studio](https://aistudio.google.com/apikey).

#### 3. Build index

Chạy lần đầu (và mỗi khi vault thay đổi nhiều):

```bash
python -m indexer.build_index
```

Index được lưu vào `data/index.json`. Thời gian build phụ thuộc số notes và quota API.

#### 4. Khởi động server

```bash
uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
```

Server sẵn sàng tại `http://localhost:8000`.

## API

### `POST /chat`

```json
// Request
{
  "question": "Sản phẩm X có bảo hành không?",
  "session_id": "optional-uuid-để-tiếp-tục-hội-thoại"
}

// Response
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "answer": "Sản phẩm X được bảo hành 12 tháng...",
  "sources": [
    { "title": "Chính sách bảo hành", "path": "chinh-sach/bao-hanh.md", "score": 0.91 }
  ],
  "latency_ms": 1240
}
```

- Không truyền `session_id` → server tự tạo UUID mới.
- Truyền lại `session_id` từ response trước → chatbot nhớ ngữ cảnh hội thoại.

### `GET /health`

```json
{ "status": "ok" }
```

### Swagger UI

```
http://localhost:8000/docs
```

## Setup MySQL (chỉ cho Cách 2 — thủ công)

> Nếu dùng Docker, MySQL đã được khởi động tự động — bỏ qua phần này.

MySQL là tuỳ chọn — chatbot vẫn chạy bình thường nếu không có DB (log chỉ lưu local JSONL).

### 1. Cài đặt MySQL

**Windows**: Tải MySQL Installer tại [mysql.com/downloads](https://dev.mysql.com/downloads/installer/), chọn "MySQL Server".

**Linux (Ubuntu/Debian)**:
```bash
sudo apt install mysql-server
sudo systemctl start mysql
```

**macOS**:
```bash
brew install mysql
brew services start mysql
```

### 2. Cấu hình chạy trên port 3307

Mặc định MySQL chạy port 3306. Dự án này dùng **3307** (tránh xung đột với MySQL instance khác).

Tìm file `my.ini` (Windows) hoặc `/etc/mysql/mysql.conf.d/mysqld.cnf` (Linux), thêm/sửa:

```ini
[mysqld]
port = 3307
```

Restart MySQL sau khi sửa:
```bash
# Windows (Services hoặc)
net stop MySQL80 && net start MySQL80

# Linux
sudo systemctl restart mysql

# macOS
brew services restart mysql
```

> Nếu muốn giữ port 3306, chỉnh `MYSQL_PORT=3306` trong `.env`.

### 3. Tạo database và user

Đăng nhập MySQL với tài khoản root:

```bash
mysql -u root -p --port 3307
```

Chạy các lệnh sau:

```sql
-- Tạo database
CREATE DATABASE chatbot_logs
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

-- Tạo user riêng cho chatbot (không dùng root)
CREATE USER 'chatbot'@'localhost' IDENTIFIED BY 'your_strong_password';

-- Cấp quyền tối thiểu (chỉ INSERT + SELECT trên database này)
GRANT SELECT, INSERT, CREATE ON chatbot_logs.* TO 'chatbot'@'localhost';

FLUSH PRIVILEGES;
EXIT;
```

> Thay `your_strong_password` bằng mật khẩu thực, rồi điền vào `MYSQL_PASSWORD` trong `.env`.

### 4. Bảng tự động tạo

**Không cần chạy CREATE TABLE thủ công.** Khi sync lần đầu, `sync_to_mysql.py` tự tạo bảng với schema:

```sql
CREATE TABLE IF NOT EXISTS conversations (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    session_id    VARCHAR(36)  NOT NULL,
    timestamp     DATETIME     NOT NULL,
    question      TEXT         NOT NULL,
    answer        TEXT         NOT NULL,
    sources       JSON,
    latency_ms    INT,
    user_feedback TINYINT      DEFAULT NULL,
    INDEX idx_session   (session_id),
    INDEX idx_timestamp (timestamp)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

### 5. Kiểm tra kết nối

```bash
python -m logs.sync_to_mysql --dry-run
```

Output thành công:
```
HH:MM:SS [sync] Không có bản ghi nào cần sync.
```

Nếu lỗi kết nối, kiểm tra lại host, port, user, password trong `.env`.

### Cách hoạt động của logging

Hệ thống logging 2 tầng để giảm attack surface:

1. **Tầng 1 — local**: Mỗi Q&A được ghi ngay vào `logs/conversations.jsonl`. Không cần DB credentials, không block request.
2. **Tầng 2 — MySQL**: Sau khi session idle **180 giây**, `auto_sync.py` tự động trigger sync. Chỉ `sync_to_mysql.py` cần credentials.

**Sync thủ công** (nếu cần):

```bash
python -m logs.sync_to_mysql            # sync tất cả bản ghi chưa sync
python -m logs.sync_to_mysql --dry-run  # xem sẽ sync bao nhiêu, không ghi thật
```

## Chuẩn bị Obsidian notes

Để chatbot trả lời chính xác, notes nên theo template:

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
```

Field `keywords` quan trọng nhất — liệt kê từ đồng nghĩa, tiếng lóng, lỗi chính tả phổ biến mà khách hay dùng.

## Rebuild index tự động

Khi vault thay đổi, dùng file watcher:

```bash
python -m indexer.watcher
```

Watcher theo dõi thư mục vault và tự rebuild index khi phát hiện file `.md` thay đổi.

## Yêu cầu hệ thống

**Docker (Cách 1):**
- Docker Desktop 4.0+
- Gemini API key
- RAM: ~700MB (app + MySQL containers)

**Thủ công (Cách 2):**
- Python 3.11+
- MySQL 8.0+ (port 3307, tuỳ chọn)
- Gemini API key
- RAM: ~500MB (index 1000 notes)
