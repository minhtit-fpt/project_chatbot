"""Build `data/product_links.json`: map { slug sản phẩm -> URL trang sản phẩm }.

Nguồn: WP REST API của CMS (`config.PRODUCT_API_URL`) — chính nơi vault được scrape.
Mỗi sản phẩm có field `pathname` (vd `/tu-dong/tu-dong-sanaky/...-vh-160vd3`); link
canonical = `config.PRODUCT_SITE_BASE` + `pathname`. Khóa = **slug** = segment cuối
của `pathname` (trùng tên file note, vd `tu-dong-sanaky-inverter-118-lit-vh-160vd3`).

KHÔNG đọc vault: lấy thẳng toàn bộ từ API rồi ghi đè file → có đủ link mọi sản phẩm,
không phụ thuộc note nào tồn tại. Tầng `prompt_builder` tra link theo *stem* của
`doc["path"]` (stem == slug), nên không cần biết cấu trúc thư mục vault.

Chạy::

    python -m indexer.build_product_links            # build/refresh map
    python -m indexer.build_product_links --dry-run  # chỉ in thống kê, không ghi file

Output (`config.PRODUCT_LINKS_PATH`)::

    { "tu-dong-sanaky-inverter-118-lit-vh-160vd3":
      "https://dienmaythienphu.vn/tu-dong/tu-dong-sanaky/...-vh-160vd3" }
"""
import argparse
import json
import ssl
import sys
import time
import urllib.error
import urllib.request

import config

_USER_AGENT = "project_chatbot-link-builder/3.0 (+local catalog sync)"
_FETCH_TIMEOUT = 30   # giây mỗi request
_PAGE_RETRIES = 2     # số lần thử lại mỗi trang khi lỗi mạng
_RETRY_WAIT = 2.0     # giây giữa các lần thử lại

# macOS (Python python.org) thiếu CA store hệ thống → dùng bundle certifi.
# Linux/Docker đã có CA hệ thống nên certifi không bắt buộc → fallback context mặc định.
try:
    import certifi
    _SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())
except ModuleNotFoundError:
    _SSL_CONTEXT = ssl.create_default_context()


def _fetch_page(paged: int) -> dict:
    """Tải 1 trang API, trả JSON đã parse. Thử lại `_PAGE_RETRIES` lần khi lỗi."""
    url = f"{config.PRODUCT_API_URL}?paged={paged}"
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    last_exc: Exception | None = None
    for attempt in range(_PAGE_RETRIES + 1):
        try:
            with urllib.request.urlopen(req, timeout=_FETCH_TIMEOUT, context=_SSL_CONTEXT) as resp:
                return json.loads(resp.read())
        except (urllib.error.URLError, json.JSONDecodeError) as exc:
            last_exc = exc
            if attempt < _PAGE_RETRIES:
                time.sleep(_RETRY_WAIT)
    raise RuntimeError(f"Không tải được trang {paged}: {last_exc}")


def _slug_of(pathname: str) -> str:
    """Segment cuối của pathname (bỏ query/fragment và dấu / cuối)."""
    path = pathname.split("?", 1)[0].split("#", 1)[0].rstrip("/")
    return path.rsplit("/", 1)[-1]


def fetch_slug_map(site_base: str) -> tuple[dict[str, str], list[str]]:
    """Phân trang toàn bộ API → map { slug -> URL canonical }.

    Trả về (slug_map, danh_sách_slug_trùng). Slug trùng → bản sau ghi đè, có cảnh báo.
    """
    first = _fetch_page(1)
    total_pages = int(first.get("totalPages", 1))
    print(f"  totals={first.get('totals')} | totalPages={total_pages}", file=sys.stderr)

    slug_map: dict[str, str] = {}
    duplicates: list[str] = []

    def _ingest(items: list[dict]) -> None:
        for it in items:
            pathname = (it.get("pathname") or "").strip()
            if not pathname:
                continue
            slug = _slug_of(pathname)
            if not slug:
                continue
            url = site_base.rstrip("/") + "/" + pathname.lstrip("/")
            if slug in slug_map and slug_map[slug] != url:
                duplicates.append(slug)
            slug_map[slug] = url

    _ingest(first.get("data", []))
    for paged in range(2, total_pages + 1):
        if paged % 25 == 0 or paged == total_pages:
            print(f"  …trang {paged}/{total_pages}", file=sys.stderr)
        _ingest(_fetch_page(paged).get("data", []))

    return slug_map, duplicates


def main() -> None:
    parser = argparse.ArgumentParser(description="Build product_links.json từ WP API.")
    parser.add_argument("--dry-run", action="store_true", help="Chỉ in thống kê, không ghi file.")
    args = parser.parse_args()

    print("→ Đọc sản phẩm từ WP API…", file=sys.stderr)
    slug_map, duplicates = fetch_slug_map(config.PRODUCT_SITE_BASE)
    print(f"  {len(slug_map)} slug duy nhất.", file=sys.stderr)
    if duplicates:
        print(f"  ⚠ {len(duplicates)} slug trùng (vd: {', '.join(sorted(set(duplicates))[:5])})",
              file=sys.stderr)

    if args.dry_run:
        print("→ --dry-run: không ghi file.", file=sys.stderr)
        return

    out = config.PRODUCT_LINKS_PATH
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(dict(sorted(slug_map.items())), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"✓ Đã ghi {len(slug_map)} link → {out}", file=sys.stderr)


if __name__ == "__main__":
    main()
