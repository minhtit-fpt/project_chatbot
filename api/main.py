import logging
import uuid
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

import config
from logs.conversation_store import log_feedback
from rag.chat_engine import answer_async, init_retriever

logger = logging.getLogger(__name__)

app = FastAPI(
    title="FAQ Chatbot API",
    version="2.0.0",
    description=(
        "API cho widget chatbot hỗ trợ khách hàng. "
        "Widget gọi POST /chat để hỏi, POST /feedback để gửi đánh giá."
    ),
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


class Source(BaseModel):
    title: str
    path: str
    score: float


class ChatResponse(BaseModel):
    message_id: str = Field(..., description="ID duy nhất của tin nhắn này, dùng để gửi feedback")
    session_id: str = Field(..., description="Giữ lại và gửi kèm các request tiếp theo trong cùng session")
    answer: str
    sources: list[Source]
    latency_ms: int
    cached: bool = False


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

@app.on_event("startup")
async def startup_event() -> None:
    try:
        await init_retriever()
    except FileNotFoundError as exc:
        logger.error("Index chưa được build: %s", exc)


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
        result = await answer_async(request.question, session_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except RuntimeError as exc:
        logger.error("Gemini API không phản hồi: %s", exc)
        raise HTTPException(
            status_code=503,
            detail="Dịch vụ AI tạm thời không khả dụng, vui lòng thử lại sau.",
        )
    except Exception as exc:
        logger.exception("Lỗi không mong đợi: %s", exc)
        raise HTTPException(status_code=500, detail=f"Lỗi xử lý: {exc}")
    return ChatResponse(**result)


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
