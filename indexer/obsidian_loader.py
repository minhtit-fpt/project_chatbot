import re
from pathlib import Path
from typing import Optional
import yaml
import config


def _should_exclude(path: Path) -> bool:
    parts = path.parts
    return any(pattern in parts for pattern in config.EXCLUDE_PATTERNS)


def _parse_frontmatter(content: str) -> tuple[dict, str]:
    """Return (metadata, body) from a markdown file with optional YAML frontmatter."""
    if not content.startswith("---"):
        return {}, content
    end = content.find("\n---", 3)
    if end == -1:
        return {}, content
    raw_yaml = content[3:end].strip()
    body = content[end + 4:].strip()
    try:
        metadata = yaml.safe_load(raw_yaml) or {}
    except yaml.YAMLError:
        metadata = {}
    return metadata, body


def _resolve_wiki_links(text: str, all_titles: dict[str, str]) -> str:
    """Replace [[link]] with the linked note title for embedding context."""
    def replace(match: re.Match) -> str:
        target = match.group(1).split("|")[0].strip()
        return all_titles.get(target.lower(), target)

    return re.sub(r"\[\[([^\]]+)\]\]", replace, text)


def _expand_embeds(text: str, vault_path: Path, visited: Optional[set] = None) -> str:
    """Recursively expand ![[embed]] references (one level deep to avoid cycles)."""
    if visited is None:
        visited = set()

    def replace(match: re.Match) -> str:
        target = match.group(1).split("|")[0].strip()
        if target in visited:
            return ""
        candidates = list(vault_path.rglob(f"{target}.md"))
        if not candidates:
            return ""
        visited.add(target)
        _, body = _parse_frontmatter(candidates[0].read_text(encoding="utf-8"))
        return body

    return re.sub(r"!\[\[([^\]]+)\]\]", replace, text)


def load_vault(vault_path: Path) -> list[dict]:
    """Load all non-excluded markdown files from the vault.

    Returns list of dicts with keys: path, title, content, metadata.
    """
    md_files = [f for f in vault_path.rglob("*.md") if not _should_exclude(f)]

    # First pass: collect all titles for wiki-link resolution
    all_titles: dict[str, str] = {}
    for f in md_files:
        raw = f.read_text(encoding="utf-8")
        meta, _ = _parse_frontmatter(raw)
        title = meta.get("title") or f.stem
        all_titles[f.stem.lower()] = title

    # Second pass: build full document records
    docs = []
    for f in md_files:
        raw = f.read_text(encoding="utf-8")
        meta, body = _parse_frontmatter(raw)
        body = _expand_embeds(body, vault_path)
        body = _resolve_wiki_links(body, all_titles)

        title = meta.get("title") or f.stem
        keywords = meta.get("keywords", [])
        if isinstance(keywords, list):
            keyword_str = " ".join(keywords)
        else:
            keyword_str = str(keywords)

        # Prepend title + keywords so embedding captures them
        content = f"{title}\n{keyword_str}\n{body}".strip()

        docs.append({
            "path": str(f.relative_to(vault_path)),
            "title": title,
            "content": content,
            "metadata": meta,
        })

    return docs
