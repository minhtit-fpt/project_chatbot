from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from rag.chat_engine import answer, get_retriever
from logs.mysql_logger import ensure_table

app = FastAPI(title="FAQ Chatbot API", version="1.0.0")

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


@app.on_event("startup")
async def startup_event() -> None:
    get_retriever()
    ensure_table()


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    try:
        result = answer(request.question)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Lỗi xử lý: {exc}")
    return ChatResponse(**result)
