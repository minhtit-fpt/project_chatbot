import logging

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from rag.chat_engine import answer, init_retriever

logger = logging.getLogger(__name__)

app = FastAPI(title="FAQ Chatbot API", version="1.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=1000)


class Source(BaseModel):
    title: str
    path: str
    score: float


class ChatResponse(BaseModel):
    answer: str
    sources: list[Source]
    latency_ms: int
    cached: bool = False


@app.on_event("startup")
async def startup_event() -> None:
    try:
        await init_retriever()
    except FileNotFoundError as exc:
        logger.error("Index chưa được build: %s", exc)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    try:
        result = await answer(request.question)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except RuntimeError as exc:
        # Gemini API thất bại sau tất cả các lần retry
        logger.error("Gemini API không phản hồi: %s", exc)
        raise HTTPException(
            status_code=503,
            detail="Dịch vụ AI tạm thời không khả dụng, vui lòng thử lại sau.",
        )
    except Exception as exc:
        logger.exception("Lỗi không mong đợi: %s", exc)
        raise HTTPException(status_code=500, detail=f"Lỗi xử lý: {exc}")
    return ChatResponse(**result)
