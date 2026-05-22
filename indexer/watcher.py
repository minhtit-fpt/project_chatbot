"""Auto re-index watcher.

Theo dõi Obsidian vault và tự động cập nhật index.json khi file .md thay đổi.
Chỉ re-embed những note bị thay đổi, không rebuild toàn bộ.

Usage:
    python -m indexer.watcher
"""
import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

import config
from indexer.obsidian_loader import load_single_file
from indexer.embedder import embed_texts

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [watcher] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


class _DateEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (datetime,)):
            return obj.isoformat()
        return super().default(obj)


def _load_index() -> dict[str, dict]:
    if not config.INDEX_PATH.exists():
        return {}
    records = json.loads(config.INDEX_PATH.read_text(encoding="utf-8"))
    return {r["path"]: r for r in records}


def _save_index(index: dict[str, dict]) -> None:
    config.INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    records = list(index.values())
    config.INDEX_PATH.write_text(
        json.dumps(records, ensure_ascii=False, cls=_DateEncoder),
        encoding="utf-8",
    )


def _reindex_file(path: Path) -> None:
    """Re-embed một file duy nhất và cập nhật index."""
    relative = str(path)
    logger.info("Re-indexing: %s", path.name)

    doc = load_single_file(path)
    if doc is None:
        logger.info("Skipped (excluded or empty): %s", path.name)
        return

    embeddings = embed_texts([doc["content"]])
    if not embeddings:
        logger.warning("Embedding failed for: %s", path.name)
        return

    index = _load_index()
    index[relative] = {
        "path": relative,
        "title": doc["title"],
        "content": doc["content"],
        "metadata": doc["metadata"],
        "embedding": embeddings[0],
    }
    _save_index(index)
    logger.info("Updated index: %s", path.name)


def _remove_from_index(path: Path) -> None:
    """Xóa note đã bị delete khỏi index."""
    relative = str(path)
    index = _load_index()
    if relative in index:
        del index[relative]
        _save_index(index)
        logger.info("Removed from index: %s", path.name)


class _VaultHandler(FileSystemEventHandler):
    def _is_md(self, event: FileSystemEvent) -> bool:
        return not event.is_directory and str(event.src_path).endswith(".md")

    def on_modified(self, event: FileSystemEvent) -> None:
        if self._is_md(event):
            _reindex_file(Path(event.src_path))

    def on_created(self, event: FileSystemEvent) -> None:
        if self._is_md(event):
            _reindex_file(Path(event.src_path))

    def on_deleted(self, event: FileSystemEvent) -> None:
        if self._is_md(event):
            _remove_from_index(Path(event.src_path))

    def on_moved(self, event: FileSystemEvent) -> None:
        # Xử lý rename/move: xóa path cũ, index path mới
        if not event.is_directory:
            old = Path(event.src_path)
            new = Path(event.dest_path)
            if old.suffix == ".md":
                _remove_from_index(old)
            if new.suffix == ".md":
                _reindex_file(new)


def start_watcher() -> None:
    vault = config.OBSIDIAN_VAULT_PATH
    logger.info("Watching vault: %s", vault)

    observer = Observer()
    observer.schedule(_VaultHandler(), str(vault), recursive=True)
    observer.start()

    try:
        while True:
            time.sleep(2)
    except KeyboardInterrupt:
        logger.info("Stopping watcher...")
    finally:
        observer.stop()
        observer.join()
        logger.info("Watcher stopped.")


if __name__ == "__main__":
    start_watcher()
