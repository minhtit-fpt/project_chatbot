"""Build or incrementally update data/index.json from the Obsidian vault.

Usage:
    python -m indexer.build_index                # full rebuild
    python -m indexer.build_index --update       # only re-embed changed notes
    python -m indexer.build_index --refresh-meta # chỉ cập nhật metadata frontmatter
                                                 # (vd featured: true), KHÔNG re-embed
"""
import datetime
import json
import sys
import time
from pathlib import Path

import config
from indexer.obsidian_loader import load_vault
from indexer.embedder import embed_texts


class _DateEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (datetime.date, datetime.datetime)):
            return obj.isoformat()
        return super().default(obj)


def build_full_index() -> None:
    print(f"[build_index] Loading vault from {config.OBSIDIAN_VAULT_PATH} ...")
    docs = load_vault(config.OBSIDIAN_VAULT_PATH)
    print(f"[build_index] {len(docs)} documents loaded")

    texts = [d["content"] for d in docs]
    total = len(texts)
    print(f"[build_index] Embedding {total} documents ...")
    t0 = time.time()
    embeddings = embed_texts(texts)
    elapsed = time.time() - t0
    rate = total / elapsed if elapsed > 0 else 0
    print(f"[build_index] Embedding done in {elapsed:.1f}s ({rate:.1f} docs/s)")

    records = []
    for doc, emb in zip(docs, embeddings):
        records.append({
            "path": doc["path"],
            "title": doc["title"],
            "content": doc["content"],
            "metadata": doc["metadata"],
            "embedding": emb,
        })

    config.INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    config.INDEX_PATH.write_text(json.dumps(records, ensure_ascii=False, cls=_DateEncoder), encoding="utf-8")
    print(f"[build_index] Saved {len(records)} records to {config.INDEX_PATH}")


def update_index() -> None:
    """Re-embed only notes that changed since the last index build."""
    if not config.INDEX_PATH.exists():
        print("[build_index] No existing index — running full build")
        build_full_index()
        return

    existing: dict[str, dict] = {}
    for rec in json.loads(config.INDEX_PATH.read_text(encoding="utf-8")):
        existing[rec["path"]] = rec

    docs = load_vault(config.OBSIDIAN_VAULT_PATH)
    changed = []
    unchanged = []

    for doc in docs:
        old = existing.get(doc["path"])
        if old is None or old["content"] != doc["content"]:
            changed.append(doc)
        else:
            unchanged.append(old)

    if not changed:
        print("[build_index] Nothing changed")
        return

    print(f"[build_index] Re-embedding {len(changed)} changed documents ...")
    embeddings = embed_texts([d["content"] for d in changed])

    updated = []
    for doc, emb in zip(changed, embeddings):
        updated.append({
            "path": doc["path"],
            "title": doc["title"],
            "content": doc["content"],
            "metadata": doc["metadata"],
            "embedding": emb,
        })

    all_records = unchanged + updated
    config.INDEX_PATH.write_text(json.dumps(all_records, ensure_ascii=False, cls=_DateEncoder), encoding="utf-8")
    print(f"[build_index] Index updated: {len(updated)} changed, {len(unchanged)} unchanged")


def refresh_metadata() -> None:
    """Cập nhật field `metadata` trong index.json từ frontmatter hiện tại của vault.

    KHÔNG re-embed — dùng khi chỉ đổi frontmatter (vd thêm `featured: true`).
    `update_index()` không dùng được cho việc này vì nó so sánh `content` (title +
    keywords + body), mà thêm `featured` không làm đổi content → bị coi là unchanged.
    """
    if not config.INDEX_PATH.exists():
        print("[build_index] No existing index — run full build first")
        return

    records = json.loads(config.INDEX_PATH.read_text(encoding="utf-8"))
    docs = load_vault(config.OBSIDIAN_VAULT_PATH)
    meta_by_path = {doc["path"]: doc["metadata"] for doc in docs}

    updated = 0
    for rec in records:
        new_meta = meta_by_path.get(rec["path"])
        if new_meta is not None and new_meta != rec.get("metadata"):
            rec["metadata"] = new_meta
            updated += 1

    config.INDEX_PATH.write_text(
        json.dumps(records, ensure_ascii=False, cls=_DateEncoder), encoding="utf-8"
    )
    print(f"[build_index] Metadata refreshed: {updated}/{len(records)} records (no re-embed)")


if __name__ == "__main__":
    if "--refresh-meta" in sys.argv:
        refresh_metadata()
    elif "--update" in sys.argv:
        update_index()
    else:
        build_full_index()
