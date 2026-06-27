1. **Lượt đầu**: gọi `POST /chat` với `session_id: null` (hoặc bỏ field) → BE tự sinh.
2. **Response trả về `session_id`** → FE lưu lại.
3. **Các lượt sau**: gửi lại đúng `session_id` đó.

```jsonc
// Request  POST /chat
{ "question": "thế nên mua loại nào", "session_id": "<id đã lưu, lượt đầu = null>" }

// Response
{ "session_id": "abc-123-uuid", "answer": [...], "message_id": "...", ... }
//  ^ lưu lại cái này, bắn lại ở lượt sau
```