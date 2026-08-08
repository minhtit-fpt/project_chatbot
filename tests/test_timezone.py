"""Tests bất biến múi giờ — mọi đồng hồ trong app phải cùng chỉ UTC+7.

Bối cảnh: `config.now_local()` cố tình trả UTC+7 cho JSONL/MySQL, nhưng container
(python:3.12-slim, không set TZ) chạy UTC. Nên các API dùng giờ local của TIẾN TRÌNH
bị lệch 7 tiếng so với record:
  - "%(asctime)s" của logging (logging.Formatter mặc định dùng time.localtime)
  - datetime.now() không tham số (eval/run_*.py)
Kết quả: dòng log 11:49 và record 18:49 là cùng một thời điểm — không đối chiếu được.
config.py đồng bộ TZ của tiến trình để chặn việc này tái diễn.
"""
import logging
import subprocess
import sys
import time
from datetime import datetime, timedelta

import config

# Sai lệch cho phép giữa hai lần đọc đồng hồ trong cùng một test.
_TOLERANCE = timedelta(seconds=5)


def test_process_local_time_matches_now_local():
    """datetime.now() (giờ local tiến trình) phải trùng now_local() (giờ ghi record)."""
    assert abs(datetime.now() - config.now_local()) < _TOLERANCE


def test_process_offset_is_utc_plus_7():
    assert datetime.now(config.TIMEZONE).strftime("%z") == "+0700"
    assert time.strftime("%z") == "+0700"


def test_logging_asctime_uses_same_clock_as_records():
    """Dòng log và record trong JSONL phải đọc được cạnh nhau, không lệch 7 tiếng."""
    record = logging.LogRecord("t", logging.INFO, "", 0, "msg", None, None)
    asctime = logging.Formatter("%(asctime)s", datefmt="%Y-%m-%dT%H:%M:%S").format(record)

    assert abs(datetime.fromisoformat(asctime) - config.now_local()) < _TOLERANCE


def _run_child(env: dict[str, str], lines: int) -> list[datetime]:
    """Chạy tiến trình Python con, trả về các mốc thời gian nó in ra."""
    code = (
        "import logging, datetime, config;"
        "r = logging.LogRecord('t', 20, '', 0, '', None, None);"
        "print(config.now_local().isoformat(timespec='seconds'));"
        "print(logging.Formatter('%(asctime)s', datefmt='%Y-%m-%dT%H:%M:%S').format(r));"
        "print(datetime.datetime.now().isoformat(timespec='seconds'))"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        env={"PATH": "/usr/bin:/bin", "HOME": "/tmp", **env},
        cwd=str(config.INDEX_PATH.parent.parent),
        check=True,
    )
    return [datetime.fromisoformat(l) for l in proc.stdout.strip().splitlines()[:lines]]


def test_timezone_survives_utc_container_environment():
    """Tiến trình mới với TZ=UTC (đúng như container) — cả 3 đồng hồ vẫn phải khớp.

    Đây là hồi quy quan trọng nhất: bug gốc chỉ hiện khi TZ của môi trường là UTC, nên
    test chạy trong tiến trình hiện tại (máy dev đã đúng giờ VN) không bắt được.
    """
    now_local, asctime, naive_now = _run_child({"TZ": "UTC"}, 3)

    assert abs(asctime - now_local) < _TOLERANCE, "logging vẫn dùng UTC trong container"
    assert abs(naive_now - now_local) < _TOLERANCE, "datetime.now() vẫn dùng UTC"


def test_app_timezone_env_var_still_overrides():
    """Đổi APP_TIMEZONE phải đổi cả giờ record LẪN giờ log, không chỉ một nửa."""
    now_local, asctime, naive_now = _run_child({"TZ": "UTC", "APP_TIMEZONE": "UTC"}, 3)

    assert abs(asctime - now_local) < _TOLERANCE
    assert abs(naive_now - now_local) < _TOLERANCE
    # APP_TIMEZONE=UTC → lệch ~7 tiếng so với giờ VN của tiến trình test này.
    assert abs((config.now_local() - now_local) - timedelta(hours=7)) < _TOLERANCE
