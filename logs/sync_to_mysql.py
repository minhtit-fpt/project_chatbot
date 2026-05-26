"""Sync conversations.jsonl → MySQL.

Chạy độc lập, không phải chatbot chạy.
Chỉ script này cần MySQL credentials.

Usage:
    python -m logs.sync_to_mysql           # sync tất cả chưa sync
    python -m logs.sync_to_mysql --dry-run # xem sẽ sync bao nhiêu bản ghi
"""
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

import mysql.connector
from mysql.connector import Error as MySQLError

import config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [sync] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

_STORE_PATH = Path(__file__).parent / "conversations.jsonl"

_CREATE_TABLE_SQL = """\
CREATE TABLE IF NOT EXISTS conversations (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    session_id    VARCHAR(36)     NOT NULL,
    timestamp     DATETIME        NOT NULL,
    question      TEXT            NOT NULL,
    answer        TEXT            NOT NULL,
    sources       JSON,
    latency_ms    INT,
    user_feedback TINYINT         DEFAULT NULL,
    INDEX idx_session  (session_id),
    INDEX idx_timestamp (timestamp)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
"""

_INSERT_SQL = """\
INSERT INTO conversations (session_id, timestamp, question, answer, sources, latency_ms)
VALUES (%s, %s, %s, %s, %s, %s)
"""


def _get_conn() -> mysql.connector.MySQLConnection:
    return mysql.connector.connect(
        host=config.MYSQL_HOST,
        port=config.MYSQL_PORT,
        user=config.MYSQL_USER,
        password=config.MYSQL_PASSWORD,
        database=config.MYSQL_DATABASE,
        connection_timeout=10,
        allow_local_infile=True,
    )


def _ensure_table(conn: mysql.connector.MySQLConnection) -> None:
    cursor = conn.cursor()
    cursor.execute(_CREATE_TABLE_SQL)
    conn.commit()
    cursor.close()


def _read_pending() -> tuple[list[dict], list[int]]:
    """Đọc tất cả bản ghi chưa sync. Trả về (records, line_indices)."""
    if not _STORE_PATH.exists():
        return [], []

    records, indices = [], []
    with _STORE_PATH.open("r", encoding="utf-8") as f:
        for i, line in enumerate(f):
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                if not rec.get("synced", False):
                    records.append(rec)
                    indices.append(i)
            except json.JSONDecodeError:
                logger.warning("Dòng %d không hợp lệ, bỏ qua", i)

    return records, indices


def _mark_synced(indices: set[int]) -> None:
    """Đánh dấu synced=true cho các dòng đã insert thành công."""
    if not _STORE_PATH.exists():
        return

    lines = _STORE_PATH.read_text(encoding="utf-8").splitlines(keepends=True)
    for i, line in enumerate(lines):
        if i in indices:
            stripped = line.strip()
            if stripped:
                try:
                    rec = json.loads(stripped)
                    rec["synced"] = True
                    lines[i] = json.dumps(rec, ensure_ascii=False) + "\n"
                except json.JSONDecodeError:
                    pass

    _STORE_PATH.write_text("".join(lines), encoding="utf-8")


def sync(dry_run: bool = False) -> None:
    records, indices = _read_pending()

    if not records:
        logger.info("Không có bản ghi nào cần sync.")
        return

    logger.info("Tìm thấy %d bản ghi chưa sync.", len(records))

    if dry_run:
        logger.info("[dry-run] Sẽ insert %d bản ghi — không thực sự ghi.", len(records))
        return

    try:
        conn = _get_conn()
    except MySQLError as exc:
        logger.error("Không kết nối được MySQL: %s", exc)
        sys.exit(1)

    _ensure_table(conn)
    cursor = conn.cursor()
    synced_indices: set[int] = set()
    ok = 0

    for rec, line_idx in zip(records, indices):
        try:
            cursor.execute(
                _INSERT_SQL,
                (
                    rec.get("session_id", ""),
                    datetime.fromisoformat(rec["timestamp"]),
                    rec["question"],
                    rec["answer"],
                    json.dumps(rec.get("sources", []), ensure_ascii=False),
                    rec.get("latency_ms"),
                ),
            )
            synced_indices.add(line_idx)
            ok += 1
        except MySQLError as exc:
            logger.warning("Insert thất bại (dòng %d): %s", line_idx, exc)

    conn.commit()
    cursor.close()
    conn.close()

    if synced_indices:
        _mark_synced(synced_indices)

    logger.info("Sync xong: %d/%d bản ghi thành công.", ok, len(records))


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    sync(dry_run=dry_run)
