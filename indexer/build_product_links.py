"""Build `data/product_links.json`: map note (path tương đối) -> URL trang sản phẩm.

Cơ chế: trang dienmaythienphu.vn có sitemap index trỏ tới nhiều sitemap con
`product-*.xml`. URL sản phẩm dạng `…/{danh-mục}/.../{slug}`, trong đó **segment
cuối (slug) trùng tên file note** (vd note `…/micro-co-day-bmb-nkn300.md` ↔
URL `…/thiet-bi-am-thanh/micro-co-day-bmb-nkn300`). Vì vậy khóa nối = slug.

Chạy::

    python -m indexer.build_product_links            # build/refresh map
    python -m indexer.build_product_links --dry-run  # chỉ in thống kê, không ghi file

Output (`config.PRODUCT_LINKS_PATH`)::

    { "thiet-bi-am-thanh/micro-co-day-bmb-nkn300.md": "https://dienmaythienphu.vn/.../micro-co-day-bmb-nkn300" }

Khóa JSON trùng đúng `path` mà retriever trả về → tầng API tra link trực tiếp
theo `doc["path"]`, không cần dò tên sản phẩm trong câu trả lời.
"""
import argparse
import gzip
import json
import ssl
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

import certifi

import config
from indexer.obsidian_loader import _should_exclude

# Namespace chuẩn của sitemaps.org (ElementTree giữ namespace trong tag).
_SITEMAP_NS = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
_USER_AGENT = "project_chatbot-link-builder/1.0 (+local catalog sync)"
_FETCH_TIMEOUT = 30  # giây mỗi request
# CA bundle của certifi — Python cài từ python.org trên macOS không có CA store hệ thống.
_SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())


def _fetch(url: str) -> bytes:
    """Tải URL, tự giải nén nếu là .gz. Raise urllib.error nếu lỗi mạng/HTTP."""
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(req, timeout=_FETCH_TIMEOUT, context=_SSL_CONTEXT) as resp:
        data = resp.read()
    if url.endswith(".gz") or data[:2] == b"\x1f\x8b":
        data = gzip.decompress(data)
    return data


def _locs(xml_bytes: bytes) -> list[str]:
    """Trả về tất cả giá trị <loc> trong một sitemap/sitemap-index."""
    root = ET.fromstring(xml_bytes)
    return [el.text.strip() for el in root.iter(f"{_SITEMAP_NS}loc") if el.text]


def _slug_of(url: str) -> str:
    """Segment cuối của URL (bỏ query/fragment và dấu / cuối)."""
    path = url.split("?", 1)[0].split("#", 1)[0].rstrip("/")
    return path.rsplit("/", 1)[-1]


def fetch_product_urls(index_url: str) -> list[str]:
    """Đọc sitemap index → gom mọi URL sản phẩm từ các sitemap con `product-*`.

    Bỏ qua `product-cat` (sitemap danh mục, không phải trang sản phẩm).
    """
    child_sitemaps = [
        loc for loc in _locs(_fetch(index_url))
        if "product-" in loc and "product-cat" not in loc
    ]
    if not child_sitemaps:
        raise RuntimeError(
            f"Không tìm thấy sitemap sản phẩm nào trong {index_url}. "
            "Site có thể đã đổi cấu trúc sitemap."
        )

    product_urls: list[str] = []
    for i, sm in enumerate(child_sitemaps, 1):
        print(f"  [{i}/{len(child_sitemaps)}] {sm}", file=sys.stderr)
        try:
            product_urls.extend(_locs(_fetch(sm)))
        except (urllib.error.URLError, ET.ParseError) as exc:
            print(f"    ! bỏ qua (lỗi: {exc})", file=sys.stderr)
    return product_urls


def build_slug_map(product_urls: list[str]) -> tuple[dict[str, str], list[str]]:
    """Map slug -> URL. Trả về (map, danh_sách_slug_trùng).

    Slug trùng (hai URL khác nhau cùng segment cuối) được ghi nhận để cảnh báo;
    bản ghi sau ghi đè bản trước.
    """
    slug_map: dict[str, str] = {}
    duplicates: list[str] = []
    for url in product_urls:
        slug = _slug_of(url)
        if not slug:
            continue
        if slug in slug_map and slug_map[slug] != url:
            duplicates.append(slug)
        slug_map[slug] = url
    return slug_map, duplicates


def match_notes(vault_path: Path, slug_map: dict[str, str]) -> tuple[dict[str, str], list[str]]:
    """Duyệt vault, khớp tên file (slug) với slug_map.

    Trả về (links keyed by path tương đối, danh_sách_note_không_khớp).
    """
    links: dict[str, str] = {}
    unmatched: list[str] = []
    for f in vault_path.rglob("*.md"):
        if _should_exclude(f):
            continue
        rel = str(f.relative_to(vault_path))
        url = slug_map.get(f.stem)
        if url:
            links[rel] = url
        else:
            unmatched.append(rel)
    return links, unmatched


def main() -> None:
    parser = argparse.ArgumentParser(description="Build product_links.json từ sitemap.")
    parser.add_argument("--dry-run", action="store_true", help="Chỉ in thống kê, không ghi file.")
    parser.add_argument("--show-unmatched", type=int, default=20,
                        help="Số note không khớp in ra để review (mặc định 20).")
    args = parser.parse_args()

    print("→ Đọc sitemap sản phẩm…", file=sys.stderr)
    product_urls = fetch_product_urls(config.PRODUCT_SITEMAP_INDEX)
    slug_map, duplicates = build_slug_map(product_urls)
    print(f"  {len(product_urls)} URL sản phẩm, {len(slug_map)} slug duy nhất.", file=sys.stderr)
    if duplicates:
        print(f"  ⚠ {len(duplicates)} slug trùng (vd: {', '.join(sorted(set(duplicates))[:5])})",
              file=sys.stderr)

    print("→ Khớp với note trong vault…", file=sys.stderr)
    links, unmatched = match_notes(config.OBSIDIAN_VAULT_PATH, slug_map)
    total = len(links) + len(unmatched)
    rate = (len(links) / total * 100) if total else 0
    print(f"  Khớp {len(links)}/{total} note ({rate:.1f}%). Không khớp: {len(unmatched)}.",
          file=sys.stderr)
    if unmatched and args.show_unmatched:
        print("  Note không khớp (mẫu):", file=sys.stderr)
        for rel in unmatched[: args.show_unmatched]:
            print(f"    - {rel}", file=sys.stderr)

    if args.dry_run:
        print("→ --dry-run: không ghi file.", file=sys.stderr)
        return

    out = config.PRODUCT_LINKS_PATH
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(dict(sorted(links.items())), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"✓ Đã ghi {len(links)} link → {out}", file=sys.stderr)


if __name__ == "__main__":
    main()
