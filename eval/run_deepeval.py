"""
eval/run_deepeval.py — Chạy DeepEval evaluation với câu hỏi đọc từ Google Sheets,
ghi kết quả (điểm, pass/fail) trở lại Sheet.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CẤU TRÚC GOOGLE SHEETS (Row 1 = header, tên phải khớp):
  A  question          — câu hỏi (bạn điền trước)
  B  expected_answer   — câu trả lời kỳ vọng (tuỳ chọn)
  C  bot_answer        — script tự điền
  D  sources           — JSON nguồn trích dẫn (script tự điền)
  E  latency_ms        — thời gian phản hồi (script tự điền)
  F  answer_relevancy  — điểm 0–1 (script tự điền)
  G  faithfulness      — điểm 0–1, chỉ có ở chế độ --direct (script tự điền)
  H  pass              — TRUE / FALSE / ERROR (script tự điền)
  I  run_at            — timestamp ISO (script tự điền)
  J  error             — thông báo lỗi nếu có (script tự điền)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
THIẾT LẬP XÁC THỰC (làm một lần):
  1. https://console.cloud.google.com → tạo / chọn project
  2. APIs & Services → Enable: "Google Sheets API", "Google Drive API"
  3. IAM & Admin → Service Accounts → Tạo service account
  4. Keys → Add Key → JSON → tải về → lưu vào  eval/service_account.json
  5. Mở Google Sheet → Share → nhập email service account → Editor

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CÀI ĐẶT:
  pip install deepeval gspread google-auth

CHẠY:
  # Chế độ direct (import module, không cần server):
  python eval/run_deepeval.py --sheet-id YOUR_SHEET_ID

  # Chế độ HTTP (cần server đang chạy):
  python eval/run_deepeval.py --sheet-id YOUR_SHEET_ID --http

  # Chạy lại tất cả (ghi đè kết quả cũ):
  python eval/run_deepeval.py --sheet-id YOUR_SHEET_ID --force

  # Worksheet tab cụ thể:
  python eval/run_deepeval.py --sheet-id YOUR_SHEET_ID --worksheet "Tháng 5"
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

# Thêm project root vào sys.path để import rag/config trong chế độ direct
sys.path.insert(0, str(Path(__file__).parent.parent))

import gspread
from google.oauth2.service_account import Credentials

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ── Vị trí cột (0-indexed) ──────────────────────────────────────────────────
# Cột input (do người dùng điền sẵn):
#   A(0)  #             — số thứ tự
#   B(1)  Danh mục      — loại câu hỏi
#   C(2)  Nhãn          — ĐÚNG / SAI (chatbot có nên biết hay không)
#   D(3)  Loại ý định   — tra cứu / tư vấn / hỏi giá / …
#   E(4)  Câu hỏi test  — INPUT của evaluation
#   F(5)  Kết quả mong đợi — expected_answer (tuỳ chọn)
#   G(6)  Ghi chú kiểm thử — cột người dùng, KHÔNG ghi đè
#
# Cột output (script tự điền bắt đầu từ H):
#   H(7)  bot_answer
#   I(8)  sources
#   J(9)  latency_ms
#   K(10) answer_relevancy
#   L(11) faithfulness
#   M(12) pass
#   N(13) run_at
#   O(14) error

COL_SO_THU_TU = 0
COL_DANH_MUC = 1
COL_NHAN = 2               # ĐÚNG / SAI
COL_LOAI_Y_DINH = 3
COL_QUESTION = 4           # E — câu hỏi
COL_EXPECTED = 5           # F — kết quả mong đợi
COL_GHI_CHU = 6            # G — ghi chú người dùng (không đụng vào)

# Output columns
COL_BOT_ANSWER = 7         # H
COL_SOURCES = 8            # I
COL_LATENCY_MS = 9         # J
COL_CORRECTNESS = 10       # K (đổi từ answer_relevancy → correctness)
COL_FAITHFULNESS = 11      # L
COL_PASS = 12              # M
COL_RUN_AT = 13            # N
COL_ERROR = 14             # O

NUM_COLS = 15
OUTPUT_HEADERS = [
    "bot_answer", "sources", "latency_ms",
    "correctness", "faithfulness", "pass", "run_at", "error",
]

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]
CREDS_PATH = Path(__file__).parent / "service_account.json"


# ── Gemini làm LLM judge cho DeepEval ───────────────────────────────────────

def make_judge():
    """Trả về GeminiJudge tích hợp config và retry của hệ thống.

    - Dùng cùng GEMINI_API_KEY và CHAT_MODEL_CHAIN từ config.py
    - Mỗi lần generate dùng call_with_retry từ rag/retry.py
    - Fallback qua từng model trong chain nếu model trước thất bại
    """
    import config as cfg
    from google import genai
    from google.genai import types
    from deepeval.models import DeepEvalBaseLLM
    from rag.retry import call_with_retry, is_retryable

    _client = genai.Client(api_key=cfg.GEMINI_API_KEY)

    class GeminiJudge(DeepEvalBaseLLM):
        def __init__(self) -> None:
            super().__init__()

        def load_model(self):
            return _client

        def _call_model(self, model: str, prompt: str, schema=None) -> str:
            kwargs: dict = {"temperature": 0}
            if schema is not None:
                kwargs["response_mime_type"] = "application/json"
                kwargs["response_schema"] = schema
            response = _client.models.generate_content(
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(**kwargs),
            )
            return response.text.strip()

        def generate(self, prompt: str, schema=None):
            """Thử lần lượt qua CHAT_MODEL_CHAIN, mỗi model retry 8 lần."""
            last_exc: Exception | None = None
            for model in cfg.CHAT_MODEL_CHAIN:
                try:
                    text = call_with_retry(
                        lambda m=model: self._call_model(m, prompt, schema),
                        max_retries=8,
                        base_wait=5.0,   # eval không cần nhanh, chờ được lâu hơn
                    )
                    if schema is not None:
                        import json as _j
                        try:
                            return schema(**_j.loads(text))
                        except Exception:
                            return text
                    return text
                except Exception as exc:
                    last_exc = exc
                    logger.warning("Judge model %s thất bại: %s", model, exc)
            raise RuntimeError("Tất cả judge models thất bại") from last_exc

        async def a_generate(self, prompt: str, schema=None):
            return await asyncio.to_thread(self.generate, prompt, schema)

        def get_model_name(self) -> str:
            return cfg.CHAT_MODEL_CHAIN[0]

    return GeminiJudge()



# ── Google Sheets helpers ────────────────────────────────────────────────────

def open_worksheet(sheet_id: str, worksheet_name: str) -> gspread.Worksheet:
    if not CREDS_PATH.exists():
        raise FileNotFoundError(
            f"Không tìm thấy {CREDS_PATH}\n"
            "Hãy tạo service account JSON và đặt vào eval/service_account.json\n"
            "Xem hướng dẫn ở đầu file này."
        )
    creds = Credentials.from_service_account_file(str(CREDS_PATH), scopes=SCOPES)
    gc = gspread.authorize(creds)
    spreadsheet = gc.open_by_key(sheet_id)
    try:
        ws = spreadsheet.worksheet(worksheet_name)
        logger.info("Đã mở worksheet: %s", worksheet_name)
    except gspread.WorksheetNotFound:
        ws = spreadsheet.sheet1
        logger.warning("Worksheet '%s' không tồn tại, dùng sheet đầu tiên: %s", worksheet_name, ws.title)
    return ws


def ensure_headers(ws: gspread.Worksheet) -> None:
    """Thêm output headers (H1:O1) nếu chưa có, không đụng vào A–G."""
    row1 = ws.row_values(1)
    # Pad để truy cập index an toàn
    while len(row1) < COL_BOT_ANSWER + 1:
        row1.append("")
    if row1[COL_BOT_ANSWER].strip().lower() != "bot_answer":
        ws.update("H1:O1", [OUTPUT_HEADERS])
        logger.info("Đã tạo output headers H1:O1")


def read_pending_rows(ws: gspread.Worksheet, force: bool) -> list[dict]:
    """Đọc các rows cần chạy evaluation."""
    all_values = ws.get_all_values()
    if len(all_values) < 2:
        return []

    rows = []
    for i, row in enumerate(all_values[1:], start=2):
        while len(row) < NUM_COLS:
            row.append("")

        question = row[COL_QUESTION].strip()
        if not question:
            continue

        bot_answer = row[COL_BOT_ANSWER].strip()
        if bot_answer and not force:
            continue  # đã chạy, bỏ qua

        rows.append({
            "row_num": i,
            "question": question,
            "expected_answer": row[COL_EXPECTED].strip(),
            # Metadata hữu ích để log
            "danh_muc": row[COL_DANH_MUC].strip(),
            "nhan": row[COL_NHAN].strip(),          # ĐÚNG / SAI
            "loai_y_dinh": row[COL_LOAI_Y_DINH].strip(),
        })
    return rows


def write_result(ws: gspread.Worksheet, row_num: int, result: dict) -> None:
    """Ghi kết quả vào columns H:O của row_num (không đụng A–G)."""
    values = [[
        result.get("bot_answer", ""),
        result.get("sources", ""),
        result.get("latency_ms", ""),
        result.get("correctness", ""),
        result.get("faithfulness", ""),
        result.get("pass", ""),
        result.get("run_at", ""),
        result.get("error", ""),
    ]]
    ws.update(f"H{row_num}:O{row_num}", values)


# ── Chatbot call ─────────────────────────────────────────────────────────────

async def call_direct(question: str) -> tuple[str, list[dict], int, list[str]]:
    """Gọi chatbot bằng cách import module trực tiếp.

    Trả về: (answer, sources, latency_ms, retrieval_context_texts)
    retrieval_context_texts dùng cho FaithfulnessMetric.
    """
    from rag.chat_engine import answer as engine_answer, _get_retriever

    # Lấy context_docs từ retriever để dùng cho FaithfulnessMetric
    retriever = await _get_retriever()
    context_docs = await asyncio.to_thread(retriever.search, question)

    retrieval_context = [
        f"{d['title']}: {d['content'][:800]}"  # giới hạn độ dài
        for d in context_docs
    ]

    result = await engine_answer(question)
    return result["answer"], result["sources"], result["latency_ms"], retrieval_context


async def call_http(question: str, api_url: str) -> tuple[str, list[dict], int, list[str]]:
    """Gọi chatbot qua HTTP endpoint /chat.

    FaithfulnessMetric sẽ không chính xác vì không có nội dung đầy đủ của nguồn.
    Chỉ dùng khi server đang chạy và không muốn import trực tiếp.
    """
    import httpx

    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(f"{api_url}/chat", json={"question": question})
        resp.raise_for_status()
        data = resp.json()

    sources = data.get("sources", [])
    # Dùng title làm proxy retrieval_context (kém chính xác hơn)
    retrieval_context = [s.get("title", "") for s in sources]

    return data["answer"], sources, data.get("latency_ms", 0), retrieval_context


# ── DeepEval evaluation ──────────────────────────────────────────────────────

def _measure_with_retry(metric, test_case) -> tuple[float | None, bool]:
    """Gọi metric.measure() với retry từ rag/retry.py.

    Trả về (score, passed). Score = None nếu thất bại sau tất cả retry.
    Dùng max_retries=8, base_wait=5.0 — phù hợp cho batch eval (không user-facing).
    """
    from rag.retry import call_with_retry

    call_with_retry(
        lambda: metric.measure(test_case),
        max_retries=8,
        base_wait=5.0,
    )
    score = metric.score
    return (round(score, 4) if score is not None else None), metric.is_successful()


def run_metrics(
    question: str,
    bot_answer: str,
    expected_answer: str,
    retrieval_context: list[str],
    judge,
) -> dict:
    """Chạy DeepEval metrics, luôn trả về score (kể cả khi fail).

    Metric chính: GEval correctness so với expected_answer (khi có).
    Fallback:     AnswerRelevancyMetric (khi không có expected_answer).
    Tham khảo:    FaithfulnessMetric (không ảnh hưởng pass/fail).

    pass = TRUE khi correctness >= 0.5.
    Score luôn có giá trị: số 0-1 khi thành công, "ERR" khi thất bại sau retry.
    """
    import time
    from deepeval.metrics import AnswerRelevancyMetric, FaithfulnessMetric, GEval
    from deepeval.test_case import LLMTestCase, LLMTestCaseParams

    test_case = LLMTestCase(
        input=question,
        actual_output=bot_answer,
        expected_output=expected_answer or None,
        retrieval_context=retrieval_context or None,
    )

    scores: dict = {"correctness": "ERR", "faithfulness": "ERR"}

    # ── Metric chính: GEval correctness (có expected) / AnswerRelevancy (không) ──
    # Dùng evaluation_steps thay vì criteria — DeepEval khuyến nghị cho non-OpenAI models
    # vì criteria đôi khi bị chia theo số steps → cho điểm cực nhỏ.
    if expected_answer:
        primary_metric = GEval(
            name="Correctness",
            evaluation_steps=[
                "So sánh actual_output với expected_output để đánh giá mức độ chính xác.",
                "Nếu actual_output đúng và đầy đủ như expected_output, cho điểm 1.0.",
                "Nếu actual_output đúng nhưng thiếu một vài chi tiết phụ, cho điểm 0.7–0.9.",
                "Nếu actual_output đúng một phần, thiếu nhiều thông tin hoặc cần hỏi thêm, cho điểm 0.4–0.6.",
                "Nếu actual_output nói 'chưa có thông tin' hoặc từ chối trả lời trong khi "
                "expected_output cho thấy cửa hàng CÓ câu trả lời rõ ràng, cho điểm 0.1–0.3.",
                "Nếu expected_output cho thấy cửa hàng KHÔNG bán hoặc KHÔNG cung cấp dịch vụ "
                "và actual_output trả lời đúng là không cung cấp, cho điểm 0.8–1.0.",
                "Nếu actual_output sai hoàn toàn hoặc mâu thuẫn với expected_output, cho điểm 0.0.",
            ],
            evaluation_params=[
                LLMTestCaseParams.INPUT,
                LLMTestCaseParams.ACTUAL_OUTPUT,
                LLMTestCaseParams.EXPECTED_OUTPUT,
            ],
            model=judge,
            threshold=0.5,
            async_mode=False,
            verbose_mode=False,
        )
    else:
        primary_metric = AnswerRelevancyMetric(
            model=judge, threshold=0.5, async_mode=False, verbose_mode=False
        )

    primary_error = False
    try:
        score, primary_passed = _measure_with_retry(primary_metric, test_case)
        scores["correctness"] = score if score is not None else "ERR"
        if not primary_passed:
            logger.debug(
                "  correctness fail (%.2f): %s",
                score or 0,
                getattr(primary_metric, "reason", ""),
            )
    except Exception as exc:
        logger.warning("Primary metric lỗi sau retry: %s", exc)
        primary_passed = False
        primary_error = True

    # Nghỉ ngắn giữa 2 metric để tránh burst
    time.sleep(3)

    # ── FaithfulnessMetric (tham khảo, không ảnh hưởng pass/fail) ─────────────
    if retrieval_context:
        faith_metric = FaithfulnessMetric(
            model=judge, threshold=0.5, async_mode=False, verbose_mode=False
        )
        try:
            faith_score, _ = _measure_with_retry(faith_metric, test_case)
            scores["faithfulness"] = faith_score if faith_score is not None else "ERR"
        except Exception as exc:
            logger.warning("FaithfulnessMetric lỗi sau retry: %s", exc)
    else:
        scores["faithfulness"] = "N/A"

    # pass: dựa vào primary metric; ERROR chỉ khi metric sập hẳn
    if primary_error:
        scores["pass"] = "ERROR"
    else:
        scores["pass"] = "TRUE" if primary_passed else "FALSE"
    return scores


# ── Main ─────────────────────────────────────────────────────────────────────

async def run_eval(args: argparse.Namespace) -> None:
    ws = open_worksheet(args.sheet_id, args.worksheet)
    ensure_headers(ws)

    rows = read_pending_rows(ws, force=args.force)
    if not rows:
        logger.info("Không có row nào cần chạy (dùng --force để chạy lại tất cả)")
        return

    logger.info("Sẽ chạy evaluation cho %d câu hỏi", len(rows))

    # Khởi tạo judge và retriever
    judge = make_judge()

    if not args.http:
        from rag.chat_engine import init_retriever
        logger.info("Đang load index vào RAM...")
        await init_retriever()

    passed = failed = errors = 0

    for i, row in enumerate(rows, start=1):
        question = row["question"]
        logger.info(
            "[%d/%d] [%s/%s] %s",
            i, len(rows),
            row.get("danh_muc", ""), row.get("nhan", ""),
            question[:80],
        )

        result: dict = {"run_at": datetime.now().isoformat(timespec="seconds")}

        try:
            if args.http:
                bot_answer, sources, latency_ms, retrieval_context = await call_http(
                    question, args.api_url
                )
            else:
                bot_answer, sources, latency_ms, retrieval_context = await call_direct(question)

            result["bot_answer"] = bot_answer
            result["sources"] = json.dumps(sources, ensure_ascii=False)
            result["latency_ms"] = latency_ms
            result["error"] = ""

            scores = run_metrics(
                question=question,
                bot_answer=bot_answer,
                expected_answer=row["expected_answer"],
                retrieval_context=retrieval_context,
                judge=judge,
            )
            result.update(scores)

            if scores["pass"] == "TRUE":
                passed += 1
                logger.info(
                    "  ✓ pass | correctness=%s faithfulness=%s latency=%dms",
                    scores.get("correctness", "n/a"),
                    scores.get("faithfulness", "n/a"),
                    latency_ms,
                )
            else:
                failed += 1
                logger.info(
                    "  ✗ fail | correctness=%s faithfulness=%s",
                    scores.get("correctness", "n/a"),
                    scores.get("faithfulness", "n/a"),
                )

        except Exception as exc:
            errors += 1
            result.update({
                "bot_answer": "",
                "sources": "",
                "latency_ms": "",
                "answer_relevancy": "",
                "faithfulness": "",
                "pass": "ERROR",
                "error": str(exc),
            })
            logger.error("  ERROR: %s", exc)

        write_result(ws, row["row_num"], result)

    total = len(rows)
    logger.info("=" * 55)
    logger.info(
        "KẾT QUẢ: %d chạy | %d pass | %d fail | %d lỗi",
        total, passed, failed, errors,
    )
    if total > 0:
        logger.info("Pass rate: %.1f%%", passed / total * 100)
    logger.info("=" * 55)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Chạy DeepEval evaluation với câu hỏi từ Google Sheets",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--sheet-id",
        required=True,
        help="Google Sheets ID (lấy từ URL: .../d/<SHEET_ID>/edit)",
    )
    parser.add_argument(
        "--worksheet",
        default="Sheet1",
        help="Tên tab worksheet (mặc định: Sheet1)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Chạy lại tất cả row, kể cả đã có kết quả",
    )
    parser.add_argument(
        "--http",
        action="store_true",
        help="Gọi chatbot qua HTTP thay vì import trực tiếp (cần server đang chạy)",
    )
    parser.add_argument(
        "--api-url",
        default="http://localhost:8000",
        help="Base URL của chatbot API (chỉ dùng với --http, mặc định: http://localhost:8000)",
    )
    args = parser.parse_args()

    asyncio.run(run_eval(args))


if __name__ == "__main__":
    main()
