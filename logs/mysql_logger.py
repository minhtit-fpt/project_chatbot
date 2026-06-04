"""MySQL conversation logger.

Tạo bảng tự động khi khởi động.
log_conversation() chạy trong thread riêng để không block request.
Lỗi kết nối sẽ được bắt và log cảnh báo — không làm sập chat.
"""
import json
import logging
import threading
from typing import Any

import mysql.connector
from mysql.connector import Error as MySQLError

import config

logger = logging.getLogger(__name__)

_init_lock = threading.Lock()
_table_ensured = False

_CREATE_TABLE_SQL = """\
CREATE TABLE IF NOT EXISTS conversations (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    timestamp     DATETIME     NOT NULL,
    question      TEXT         NOT NULL,
    answer        TEXT         NOT NULL,
    sources       JSON,
    latency_ms    INT,
    user_feedback TINYINT      DEFAULT NULL,
    INDEX idx_timestamp (timestamp)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
"""

_INSERT_SQL = """\
INSERT INTO conversations (timestamp, question, answer, sources, latency_ms)
VALUES (%s, %s, %s, %s, %s)
"""


def _get_conn() -> mysql.connector.MySQLConnection:
    return mysql.connector.connect(
        host=config.MYSQL_HOST,
        port=config.MYSQL_PORT,
        user=config.MYSQL_USER,
        password=config.MYSQL_PASSWORD,
        database=config.MYSQL_DATABASE,
        connection_timeout=5,
    )


def ensure_table() -> None:
    """Gọi 1 lần khi startup — tạo bảng nếu chưa có."""
    global _table_ensured
    with _init_lock:
        if _table_ensured:
            return
        try:
            conn = _get_conn()
            cursor = conn.cursor()
            cursor.execute(_CREATE_TABLE_SQL)
            conn.commit()
            cursor.close()
            conn.close()
            _table_ensured = True
            logger.info("MySQL logger ready (host=%s db=%s)", config.MYSQL_HOST, config.MYSQL_DATABASE)
        except MySQLError as exc:
            logger.warning("MySQL logger init failed — logging disabled: %s", exc)


def _do_log(question: str, answer: str, sources: list[Any], latency_ms: int) -> None:
    try:
        conn = _get_conn()
        cursor = conn.cursor()
        cursor.execute(
            _INSERT_SQL,
            (
                config.now_local(),
                question,
                answer,
                json.dumps(sources, ensure_ascii=False),
                latency_ms,
            ),
        )
        conn.commit()
        cursor.close()
        conn.close()
    except MySQLError as exc:
        logger.warning("MySQL log failed: %s", exc)


def log_conversation(question: str, answer: str, sources: list[Any], latency_ms: int) -> None:
    """Ghi log Q&A ra MySQL trong background thread — non-blocking."""
    t = threading.Thread(
        target=_do_log,
        args=(question, answer, sources, latency_ms),
        daemon=True,
    )
    t.start()
