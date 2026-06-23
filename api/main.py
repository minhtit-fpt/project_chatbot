import logging
import uuid
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

import config
from api.formatting import format_answer_lines
from logs.conversation_store import log_feedback
from rag.chat_engine import answer_async, init_retriever
from rag.retry import is_retryable

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Pre-warm index vào RAM khi khởi động (thay cho on_event đã deprecated).
    try:
        await init_retriever()
    except FileNotFoundError as exc:
        logger.error("Index chưa được build: %s", exc)
    yield


app = FastAPI(
    title="FAQ Chatbot API",
    version="2.0.0",
    description=(
        "API cho widget chatbot hỗ trợ khách hàng. "
        "Widget gọi POST /chat để hỏi, POST /feedback để gửi đánh giá."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.ALLOWED_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=1000)
    session_id: str | None = Field(
        default=None,
        description="UUID của session hiện tại. Bỏ trống để tạo session mới.",
    )
    test: bool = Field(
        default=False,
        description="Nếu True, không ghi log vào JSONL/MySQL (dùng khi test thử).",
    )


class ChatResponse(BaseModel):
    message_id: str = Field(..., description="ID duy nhất của tin nhắn này, dùng để gửi feedback")
    session_id: str = Field(..., description="Giữ lại và gửi kèm các request tiếp theo trong cùng session")
    answer: list[str] = Field(
        ...,
        description="Câu trả lời — mỗi phần tử là MỘT dòng đã làm sạch khoảng trắng. FE tự xuống dòng/style.",
    )
    latency_ms: int
    cached: bool = False
    # Lưu ý: `sources` (nguồn trích dẫn) CỐ TÌNH không nằm trong response.
    # Nguồn vẫn được ghi vào log/DB qua log_conversation() trong rag/chat_engine.py,
    # nhưng không trả về cho người dùng cuối.


class SessionResponse(BaseModel):
    session_id: str


class FeedbackRequest(BaseModel):
    message_id: str = Field(..., description="message_id lấy từ response của POST /chat")
    session_id: str
    rating: Literal["up", "down"]
    comment: str | None = Field(default=None, max_length=500)


class FeedbackResponse(BaseModel):
    ok: bool


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health", summary="Health check")
async def health() -> dict:
    return {"status": "ok"}


@app.get(
    "/session",
    response_model=SessionResponse,
    summary="Tạo session mới",
    description="Widget gọi endpoint này khi user mở chat lần đầu để lấy session_id.",
)
async def new_session() -> SessionResponse:
    return SessionResponse(session_id=str(uuid.uuid4()))


@app.post(
    "/chat",
    response_model=ChatResponse,
    summary="Gửi câu hỏi và nhận câu trả lời",
)
async def chat(request: ChatRequest) -> ChatResponse:
    session_id = request.session_id or str(uuid.uuid4())
    try:
        result = await answer_async(request.question, session_id, skip_log=request.test)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except RuntimeError as exc:
        logger.error("Gemini API không phản hồi: %s", exc)
        raise HTTPException(
            status_code=503,
            detail="Dịch vụ AI tạm thời không khả dụng, vui lòng thử lại sau.",
        )
    except Exception as exc:
        # Gemini trả ServerError 503 (quá tải) là lỗi transient nhưng KHÔNG phải
        # RuntimeError → nếu để rơi xuống nhánh 500 dưới, người dùng thấy "Lỗi xử lý
        # nội bộ" thay vì thông báo bận tạm thời. Map lỗi retryable → 503.
        if is_retryable(exc):
            logger.warning("Gemini tạm thời quá tải: %s", exc)
            raise HTTPException(
                status_code=503,
                detail="Dịch vụ AI đang bận, vui lòng thử lại sau giây lát.",
            )
        # Không nhét nội dung exception vào response (tránh rò chi tiết nội bộ);
        # chi tiết đã được ghi server-side qua logger.exception.
        logger.exception("Lỗi không mong đợi: %s", exc)
        raise HTTPException(status_code=500, detail="Lỗi xử lý nội bộ, vui lòng thử lại sau.")
    # answer (chuỗi nhiều dòng từ LLM) → mảng từng dòng đã làm sạch cho FE.
    # Bản text đầy đủ vẫn được log ở DB (trong chat_engine.answer()).
    # Tạo dict mới (không mutate `result`); key "sources" dư bị Pydantic bỏ qua.
    payload = {**result, "answer": format_answer_lines(result["answer"])}
    return ChatResponse(**payload)


@app.post(
    "/feedback",
    response_model=FeedbackResponse,
    summary="Gửi đánh giá cho một câu trả lời",
    description=(
        "Widget gọi endpoint này sau khi user bấm thumbs up/down. "
        "message_id lấy từ field message_id trong response của POST /chat."
    ),
)
async def feedback(request: FeedbackRequest) -> FeedbackResponse:
    log_feedback(
        message_id=request.message_id,
        session_id=request.session_id,
        rating=request.rating,
        comment=request.comment,
    )
    return FeedbackResponse(ok=True)
