from __future__ import annotations

import asyncio
import hashlib
import html
import json
import os
import re
import shutil
import sys
import tempfile
import time
import unicodedata
import urllib.parse
import urllib.request
import uuid
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict, deque
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Iterable


VERSION = "0.2.0"
DEFAULT_INVENTORY_LIMIT = 2000
DEFAULT_PAGE_LIMIT = 250
SUPPORTED_SUFFIXES = {
    ".html": "html", ".htm": "html", ".md": "markdown", ".markdown": "markdown",
    ".txt": "text", ".pdf": "pdf", ".png": "image", ".jpg": "image",
    ".jpeg": "image", ".webp": "image", ".tif": "image", ".tiff": "image",
}
NOISE_SEGMENTS = {
    "account", "admin", "author", "authors", "cart", "checkout", "contact", "feed",
    "legal", "login", "privacy", "register", "search", "signin", "signup", "tag", "tags", "terms",
    "upload", "uploads", "images", "image", "img", "assets", "static", "wp-content", "wp-includes",
    "מדיניות-פרטיות", "תקנון", "תקנון-שימוש", "צור-קשר", "התחברות", "הרשמה", "סל-קניות",
}
PROMO_RE = re.compile(
    r"(?:\b(?:buy now|shop now|subscribe|sign up|register now|book (?:a |your )?(?:call|session|consultation)|"
    r"contact (?:us|sales)|call (?:us|now)|limited time|special offer|discount|coupon|free trial|"
    r"follow us|share (?:this|on)|download (?:our|the) (?:free|guide)|join (?:our|the) (?:newsletter|community)|"
    r"קנו עכשיו|הירשמו|הרשמה|מבצע|הנחה|צרו קשר|עקבו אחרינו|שתפו|הצטרפו)\b)", re.IGNORECASE,
)
BYLINE_RE = re.compile(r"^(?:by|author|written by|reviewed by|posted by|מאת|נכתב על ידי|כותב(?:ת)?):?\s+.{2,100}$", re.IGNORECASE)
CONTACT_RE = re.compile(
    r"(?:[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}|(?:https?://)?(?:www\.)?(?:facebook|instagram|linkedin|tiktok|x|twitter)\.com/\S+|(?<!\d)(?:\+?\d[\d ()\-.]{7,}\d)(?!\d))",
    re.IGNORECASE,
)
LOCAL_PATH_RE = re.compile(r"(?:[A-Za-z]:\\|/Users/|/home/|file://)", re.IGNORECASE)
URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)
RAW_HTML_RE = re.compile(r"</?[A-Za-z][^>]*>")
IMAGE_MD_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
LINK_MD_RE = re.compile(r"\[([^\]]+)\]\([^)]*\)")
SENSITIVE_RE = re.compile(
    r"\b(?:diagnos(?:is|e)|treat(?:ment|s|ed)?|cure[sd]?|prescription|dosage|contraindicat|pregnan|disease|syndrome|injur|medication)\b|"
    r"(?:אבחון|טיפול|מרשם|מינון|תרופה|מחלה|פציעה|הריון)", re.IGNORECASE,
)
HEBREW_FILENAME_TRANSLITERATION = str.maketrans({
    "א": "a", "ב": "b", "ג": "g", "ד": "d", "ה": "h", "ו": "v", "ז": "z", "ח": "h",
    "ט": "t", "י": "y", "כ": "k", "ך": "k", "ל": "l", "מ": "m", "ם": "m", "נ": "n",
    "ן": "n", "ס": "s", "ע": "a", "פ": "p", "ף": "f", "צ": "ts", "ץ": "ts", "ק": "k",
    "ר": "r", "ש": "sh", "ת": "t",
})


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def stable_id(namespace: str, value: str, length: int = 16) -> str:
    return digest(f"{namespace}::{value}".encode())[:length]


def atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temp.write_text(text, encoding="utf-8", newline="\n")
    for attempt in range(10):
        try:
            os.replace(temp, path)
            return
        except OSError:
            if attempt == 9:
                raise
            time.sleep(0.05 * (attempt + 1))


def atomic_json(path: Path, value: Any) -> None:
    atomic_text(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    atomic_text(path, "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    for number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        if line.strip():
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"Expected an object at {path}:{number}")
            rows.append(value)
    return rows


def slug(value: str, limit: int = 72) -> str:
    value = value.encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", value).strip("-")[:limit].strip("-") or "source"


def unicode_slug(value: str, limit: int = 72) -> str:
    unquoted = urllib.parse.unquote(value or "").strip()
    norm = unicodedata.normalize("NFKC", unquoted)
    cleaned = re.sub(r"[^\w\s-]+", "-", norm, flags=re.UNICODE)
    cleaned = re.sub(r"[\s_]+", "-", cleaned).strip("-").lower()
    return cleaned[:limit].strip("-") or "general"


def portable_article_slug(value: str, limit: int = 80) -> str:
    """Return a readable ASCII filename stem that is safe across platforms."""
    normalized = unicodedata.normalize("NFKD", (value or "").translate(HEBREW_FILENAME_TRANSLITERATION))
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii").lower()
    cleaned = re.sub(r"[^a-z0-9]+", "-", ascii_value).strip("-")
    return cleaned[:limit].rstrip("-") or "knowledge"


def clean_url(url: str) -> str:
    parts = urllib.parse.urlsplit(url)
    query = [(k, v) for k, v in urllib.parse.parse_qsl(parts.query) if not k.lower().startswith(("utm_", "fbclid", "gclid"))]
    path = re.sub(r"/{2,}", "/", parts.path or "/")
    return urllib.parse.urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, urllib.parse.urlencode(query), ""))


def kind_of(source: str) -> str:
    parts = urllib.parse.urlsplit(source)
    if parts.scheme in {"http", "https"} and parts.netloc:
        return "website"
    path = Path(source).expanduser().resolve()
    if not path.is_file():
        raise ValueError(f"Source not found: {path}")
    kind = SUPPORTED_SUFFIXES.get(path.suffix.lower())
    if not kind:
        raise ValueError(f"Unsupported source type: {path.suffix}")
    return kind


def canonical_source(source: str, kind: str) -> str:
    return clean_url(source) if kind == "website" else str(Path(source).expanduser().resolve())


def source_name(source: str, kind: str) -> str:
    if kind == "website":
        host = urllib.parse.urlsplit(source).hostname or "website"
        return slug(host.removeprefix("www."))
    return slug(Path(source).stem)


def run_root(workspace: Path) -> Path:
    return workspace / ".knowledge-intake" / "runs"


def run_path(workspace: Path, name: str) -> Path:
    candidate = (run_root(workspace) / slug(name)).resolve()
    if candidate.parent != run_root(workspace).resolve() or not (candidate / "run.json").exists():
        raise ValueError(f"Unknown intake: {name}")
    return candidate


def load_run(path: Path) -> dict[str, Any]:
    return json.loads((path / "run.json").read_text(encoding="utf-8"))


def save_run(path: Path, run: dict[str, Any]) -> None:
    run["updated_at"] = now()
    atomic_json(path / "run.json", run)
    atomic_json(path / "status.json", public_state(path, run))
    render_report(path)


def publish_progress(path: Path, run: dict[str, Any]) -> None:
    """Refresh the lightweight dashboard state without rebuilding report assets."""
    run["updated_at"] = now()
    atomic_json(path / "run.json", run)
    atomic_json(path / "status.json", public_state(path, run))


class LinksParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[str] = []
        self.title = ""
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "a":
            href = dict(attrs).get("href")
            if href:
                self.links.append(href)
        if tag.lower() == "title":
            self._in_title = True

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title += data


class TextParser(HTMLParser):
    SKIP = {"script", "style", "noscript", "svg", "canvas", "nav", "footer", "form"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skip = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in self.SKIP:
            self.skip += 1
        elif not self.skip and re.fullmatch(r"h[1-6]", tag):
            self.parts.append("\n\n" + "#" * int(tag[1]) + " ")
        elif not self.skip and tag == "li":
            self.parts.append("\n- ")
        elif not self.skip and tag in {"p", "div", "section", "article", "main", "blockquote", "br", "tr"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in self.SKIP and self.skip:
            self.skip -= 1
        elif not self.skip and (tag in {"p", "div", "section", "article", "main", "blockquote", "tr"} or re.fullmatch(r"h[1-6]", tag)):
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self.skip:
            self.parts.append(data)


def fetch(url: str, timeout: int = 15) -> tuple[bytes, str]:
    request = urllib.request.Request(url, headers={"User-Agent": "KnowledgeIntake/0.2 (+local inventory)"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read(8 * 1024 * 1024), response.headers.get_content_type()


def sitemap_urls(root_url: str, limit: int) -> list[str]:
    base = urllib.parse.urlsplit(root_url)
    origin = f"{base.scheme}://{base.netloc}"
    candidates = [f"{origin}/sitemap.xml"]
    try:
        robots, _ = fetch(f"{origin}/robots.txt", 8)
        for line in robots.decode("utf-8", "replace").splitlines():
            if line.lower().startswith("sitemap:"):
                candidates.append(line.split(":", 1)[1].strip())
    except Exception:
        pass
    found: list[str] = []
    queue = deque(dict.fromkeys(candidates))
    seen_maps: set[str] = set()
    while queue and len(found) < limit:
        map_url = queue.popleft()
        if map_url in seen_maps:
            continue
        seen_maps.add(map_url)
        try:
            data, _ = fetch(map_url, 15)
            root = ET.fromstring(data)
        except Exception:
            continue
        locations = [node.text.strip() for node in root.iter() if node.tag.endswith("loc") and node.text]
        if root.tag.endswith("sitemapindex"):
            queue.extend(locations)
        else:
            found.extend(locations)
    return found[:limit]


def inventory_group(url: str) -> tuple[str, bool]:
    path = urllib.parse.unquote(urllib.parse.urlsplit(url).path)
    segments = [unicode_slug(x) for x in path.split("/") if x]
    group = segments[0] if segments else "home"
    noisy = group in NOISE_SEGMENTS or any(segment in NOISE_SEGMENTS for segment in segments)
    return group, not noisy


def inventory_site(url: str, limit: int) -> list[dict[str, Any]]:
    origin_host = (urllib.parse.urlsplit(url).hostname or "").lower()
    urls = sitemap_urls(url, limit)
    if not urls:
        queue = deque([clean_url(url)])
        seen: set[str] = set()
        while queue and len(seen) < min(limit, 500):
            current = queue.popleft()
            if current in seen:
                continue
            seen.add(current)
            try:
                data, content_type = fetch(current, 12)
            except Exception:
                continue
            if content_type != "text/html":
                continue
            parser = LinksParser()
            parser.feed(data.decode("utf-8", "replace"))
            for href in parser.links:
                candidate = clean_url(urllib.parse.urljoin(current, href))
                parts = urllib.parse.urlsplit(candidate)
                if (parts.hostname or "").lower() == origin_host and parts.scheme in {"http", "https"}:
                    if not re.search(r"\.(?:zip|exe|dmg|mp4|mp3|mov|avi|css|js|woff2?)(?:$|\?)", parts.path, re.I):
                        queue.append(candidate)
        urls = list(seen)
    valid_candidates = []
    seen_urls: set[str] = set()
    for value in urls:
        candidate = clean_url(value)
        parts = urllib.parse.urlsplit(candidate)
        if (parts.hostname or "").lower() != origin_host or candidate in seen_urls:
            continue
        seen_urls.add(candidate)
        group, recommended = inventory_group(candidate)
        label = urllib.parse.unquote(parts.path.strip("/").split("/")[-1] or origin_host).replace("-", " ").replace("_", " ")
        valid_candidates.append({
            "url": candidate, "group": group, "label": label[:160], "recommended": recommended,
            "selected": False, "status": "discovered",
        })

    group_counts = Counter(row["group"] for row in valid_candidates)
    for row in valid_candidates:
        if group_counts[row["group"]] < 2:
            row["group"] = "pages"

    return sorted(valid_candidates, key=lambda row: (row["group"], row["url"]))[:limit]


def start(workspace: Path, source: str, *, name: str | None = None, inventory_limit: int = DEFAULT_INVENTORY_LIMIT) -> tuple[Path, dict[str, Any]]:
    kind = kind_of(source)
    canonical = canonical_source(source, kind)
    run_name = slug(name) if name else source_name(canonical, kind)
    path = run_root(workspace) / run_name
    if path.exists():
        if (path / "run.json").exists() and load_run(path)["source"] != canonical:
            raise ValueError(f"Run name '{run_name}' already belongs to another source. Use --name.")
        archive_root = workspace / ".knowledge-intake" / "archive"
        archive_root.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        archived = archive_root / f"{run_name}-{stamp}-{uuid.uuid4().hex[:6]}"
        os.replace(path, archived)
    for folder in ("evidence/source", "evidence/pages", "evidence/media", "prepared", "agent", "manifests", "reports"):
        (path / folder).mkdir(parents=True, exist_ok=True)
    if kind == "website":
        inventory = inventory_site(canonical, inventory_limit)
        status = "discovered"
    else:
        source_path = Path(canonical)
        target = path / "evidence" / "source" / source_path.name
        shutil.copy2(source_path, target)
        inventory = [{"url": canonical, "group": kind, "label": source_path.name, "recommended": True, "selected": True, "status": "selected"}]
        status = "selected"
    write_jsonl(path / "inventory.jsonl", inventory)
    atomic_json(path / "selection.json", {"saved_at": None, "urls": [row["url"] for row in inventory if row["selected"]]})
    run = {
        "schema_version": "knowledge-intake-run-v2", "processor_version": VERSION, "run_name": run_name,
        "source": canonical, "source_kind": kind, "created_at": now(), "updated_at": now(),
        "status": status, "inventory_count": len(inventory), "selected_count": sum(row["selected"] for row in inventory),
        "counts": {"found": 0, "cleaned": 0, "review": 0, "ready": 0, "excluded": 0},
        "message": "Choose the useful website sections, then save the selection." if kind == "website" else "The source is selected and ready to collect.",
        "events": [{"at": now(), "stage": "discover", "message": f"Found {len(inventory)} endpoint(s)."}],
    }
    save_run(path, run)
    return path, run


def save_selection(path: Path, urls: list[str]) -> dict[str, Any]:
    inventory = read_jsonl(path / "inventory.jsonl")
    known = {row["url"] for row in inventory}
    chosen = list(dict.fromkeys(clean_url(url) for url in urls if clean_url(url) in known))
    if not chosen:
        raise ValueError("Selection is empty.")
    chosen_set = set(chosen)
    for row in inventory:
        row["selected"] = row["url"] in chosen_set
        row["status"] = "selected" if row["selected"] else "discovered"
    write_jsonl(path / "inventory.jsonl", inventory)
    atomic_json(path / "selection.json", {"saved_at": now(), "urls": chosen})
    run = load_run(path)
    run["status"] = "selected"
    run["selected_count"] = len(chosen)
    run["message"] = f"{len(chosen)} page(s) selected. Collection can start."
    run["events"].append({"at": now(), "stage": "select", "message": run["message"]})
    save_run(path, run)
    return run


def select_patterns(path: Path, patterns: list[str], recommended: bool = False) -> dict[str, Any]:
    import fnmatch
    inventory = read_jsonl(path / "inventory.jsonl")
    urls = []
    for row in inventory:
        parsed = urllib.parse.urlsplit(row["url"])
        if recommended and row["recommended"]:
            urls.append(row["url"])
        elif any(fnmatch.fnmatch(parsed.path, pattern) or fnmatch.fnmatch(row["url"], pattern) or row["group"] == pattern for pattern in patterns):
            urls.append(row["url"])
    return save_selection(path, urls)


def title_from(markdown: str, fallback: str) -> str:
    match = re.search(r"(?m)^#\s+(.+)$", markdown)
    if match:
        return re.sub(r"[*_`]+", "", match.group(1)).strip()[:180]
    for line in markdown.splitlines():
        plain = re.sub(r"^[#>*+\-\d.\s]+", "", line).strip()
        if len(plain) > 5:
            return plain[:180]
    return fallback


def basic_clean(markdown: str, title: str, *, public: bool = False) -> str:
    text = html.unescape(markdown.replace("\r\n", "\n").replace("\r", "\n")).replace("\x00", "")
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    text = IMAGE_MD_RE.sub("", text)
    text = LINK_MD_RE.sub(r"\1", text)
    text = RAW_HTML_RE.sub("", text)
    kept = []
    for raw in text.splitlines():
        line = re.sub(r"[ \t]+", " ", raw).strip()
        plain = re.sub(r"^[#>*+\-\d.\s]+", "", line).strip()
        if not line or (not BYLINE_RE.match(plain) and not PROMO_RE.search(plain) and not CONTACT_RE.search(plain)):
            if public:
                line = CONTACT_RE.sub("", line)
                line = LOCAL_PATH_RE.sub("", line)
                line = URL_RE.sub("", line)
            kept.append(line.rstrip())
    text = re.sub(r"\n{3,}", "\n\n", "\n".join(kept)).strip()
    text = re.sub(r"(?m)^#\s+.*$", "", text, count=1).strip()
    text = re.sub(r"(?m)^#\s+", "## ", text)
    safe_title = re.sub(r"[#\r\n]+", " ", title).strip() or "Knowledge document"
    return f"# {safe_title}\n\n{text}\n"


def line_key(line: str) -> str:
    line = re.sub(r"^[#>*+\-\d.\s]+", "", line).lower()
    return re.sub(r"\W+", " ", line, flags=re.UNICODE).strip()


def remove_shared_noise(documents: list[dict[str, Any]], path: Path) -> None:
    if len(documents) < 3:
        return
    occurrences: Counter[str] = Counter()
    for doc in documents:
        text = (path / doc["prepared_path"]).read_text(encoding="utf-8")
        occurrences.update({line_key(line) for line in text.splitlines() if 3 <= len(line_key(line)) <= 120})
    threshold = max(3, int(len(documents) * 0.35 + 0.999))
    repeated = {key for key, count in occurrences.items() if count >= threshold}
    for doc in documents:
        target = path / doc["prepared_path"]
        lines = target.read_text(encoding="utf-8").splitlines()
        title_line = lines[0] if lines else f"# {doc['title']}"
        cleaned = [title_line] + [line for line in lines[1:] if not (line_key(line) in repeated and not line.startswith("## "))]
        atomic_text(target, re.sub(r"\n{3,}", "\n\n", "\n".join(cleaned)).strip() + "\n")


def classify(locator: str, title: str, markdown: str, prepared_path: str, source_type: str, evidence: list[str]) -> dict[str, Any]:
    doc_id = stable_id("knowledge-intake-doc-v2", locator)
    words = len(re.findall(r"\w+", markdown, re.UNICODE))
    lane, reasons = "included", []
    if words < 45:
        lane = "needs_agent" if source_type in {"pdf", "image"} else "excluded"
        reasons.append("Too little reliable standalone information")
    if SENSITIVE_RE.search(markdown):
        lane = "sensitive_review"
        reasons.append("Contains a health-sensitive claim")
    if CONTACT_RE.search(markdown) or LOCAL_PATH_RE.search(markdown):
        lane = "needs_agent"
        reasons.append("Identity-shaped or private-path residue needs review")
    return {
        "schema_version": "knowledge-intake-document-v2", "document_id": doc_id,
        "public_id": stable_id("knowledge-intake-public-v2", doc_id), "canonical_locator": locator,
        "title": title, "language": "he" if len(re.findall(r"[\u0590-\u05FF]", markdown)) > len(re.findall(r"[A-Za-z]", markdown)) * .35 else "en",
        "source_type": source_type, "prepared_path": prepared_path, "content_sha256": digest(markdown.encode()),
        "word_count": words, "lane": lane, "reasons": reasons, "evidence": evidence,
    }


async def crawl_selected(path: Path, urls: list[str], run: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    try:
        from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode
        from crawl4ai.async_dispatcher import MemoryAdaptiveDispatcher
        from crawl4ai.content_filter_strategy import PruningContentFilter
        from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator
    except ImportError as exc:
        raise RuntimeError("Crawl4AI is missing. Run the setup command from doctor.") from exc
    browser = BrowserConfig(headless=True, light_mode=True, avoid_ads=True, verbose=False)
    config = CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS, word_count_threshold=10,
        excluded_tags=["script", "style", "nav", "footer", "form"], remove_overlay_elements=True,
        remove_consent_popups=True, process_iframes=True, check_robots_txt=True,
        markdown_generator=DefaultMarkdownGenerator(content_filter=PruningContentFilter(threshold=.45)),
        stream=True,
    )
    dispatcher = MemoryAdaptiveDispatcher(max_session_permit=5)
    documents, evidence = [], []
    async with AsyncWebCrawler(config=browser) as crawler:
        results = await crawler.arun_many(urls, config=config, dispatcher=dispatcher)
        async for result in results:
            index = len(documents) + 1
            url = clean_url(result.url or urls[min(index - 1, len(urls) - 1)])
            if not result.success:
                documents.append({**classify(url, url, "", "", "website", []), "lane": "failed", "reasons": [str(result.error_message)[:240]]})
            else:
                doc_id = stable_id("knowledge-intake-doc-v2", url)
                raw_path = path / "evidence" / "pages" / f"{doc_id}.html"
                atomic_text(raw_path, result.html or "")
                evidence.append({"locator": url, "path": raw_path.relative_to(path).as_posix(), "sha256": digest(raw_path.read_bytes()), "observed_at": now()})
                md_obj = result.markdown
                markdown = getattr(md_obj, "fit_markdown", "") or getattr(md_obj, "raw_markdown", "") or str(md_obj or "")
                fallback = urllib.parse.unquote(urllib.parse.urlsplit(url).path.rstrip("/").split("/")[-1] or urllib.parse.urlsplit(url).netloc).replace("-", " ")
                title = title_from(markdown, fallback)
                cleaned = basic_clean(markdown, title)
                prepared = path / "prepared" / f"{doc_id}.md"
                atomic_text(prepared, cleaned)
                documents.append(classify(url, title, cleaned, prepared.relative_to(path).as_posix(), "website", [raw_path.relative_to(path).as_posix()]))
            run["counts"] = counts(documents)
            run["message"] = f"Read {index}/{len(urls)} selected pages."
            if index % 10 == 0 or index == len(urls):
                run["events"].append({"at": now(), "stage": "collect", "message": run["message"]})
                publish_progress(path, run)
    return documents, evidence


def collect_local(path: Path, run: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    source = Path(run["source"])
    evidence_file = next((path / "evidence" / "source").iterdir())
    evidence = [{"locator": run["source"], "path": evidence_file.relative_to(path).as_posix(), "sha256": digest(evidence_file.read_bytes()), "observed_at": now()}]
    kind = run["source_kind"]
    markdown = ""
    if kind in {"markdown", "text"}:
        markdown = evidence_file.read_text(encoding="utf-8-sig", errors="replace")
    elif kind == "html":
        parser = TextParser()
        parser.feed(evidence_file.read_text(encoding="utf-8-sig", errors="replace"))
        markdown = "".join(parser.parts)
    elif kind == "pdf":
        try:
            from pypdf import PdfReader
            markdown = "\n\n".join((page.extract_text() or "") for page in PdfReader(str(evidence_file)).pages)
        except Exception:
            markdown = ""
    title = title_from(markdown, source.stem)
    doc_id = stable_id("knowledge-intake-doc-v2", run["source"])
    prepared = path / "prepared" / f"{doc_id}.md"
    cleaned = basic_clean(markdown, title) if markdown else f"# {title}\n"
    atomic_text(prepared, cleaned)
    doc = classify(run["source"], title, cleaned, prepared.relative_to(path).as_posix(), kind, [evidence_file.relative_to(path).as_posix()])
    if kind == "image" or (kind == "pdf" and doc["word_count"] < 45):
        doc["lane"] = "needs_agent"
        doc["reasons"] = ["The coding agent needs to read this scan or image"]
    return [doc], evidence


def update_manifests(path: Path, documents: list[dict[str, Any]], evidence: list[dict[str, Any]]) -> None:
    hashes: dict[str, str] = {}
    for doc in documents:
        if doc["lane"] == "included":
            if doc["content_sha256"] in hashes:
                doc["lane"] = "excluded"
                doc["reasons"] = [f"Duplicate of {hashes[doc['content_sha256']]}" ]
            else:
                hashes[doc["content_sha256"]] = doc["document_id"]
    write_jsonl(path / "manifests" / "documents.jsonl", documents)
    write_jsonl(path / "manifests" / "source_snapshot.jsonl", evidence)
    queue = []
    for doc in documents:
        if doc["lane"] in {"needs_agent", "sensitive_review", "failed"}:
            queue.append({
                "task_id": "task-" + stable_id("knowledge-intake-task-v2", doc["document_id"] + doc["lane"], 12),
                "document_id": doc["document_id"], "kind": doc["lane"], "title": doc["title"],
                "reason": "; ".join(doc["reasons"]), "evidence": doc["evidence"],
            })
    write_jsonl(path / "manifests" / "review_queue.jsonl", queue)


def counts(documents: list[dict[str, Any]]) -> dict[str, int]:
    lanes = Counter(doc["lane"] for doc in documents)
    return {
        "found": len(documents), "cleaned": sum(bool(doc.get("prepared_path")) for doc in documents),
        "review": lanes["needs_agent"] + lanes["sensitive_review"] + lanes["failed"],
        "ready": lanes["included"], "excluded": lanes["excluded"],
    }


def collect(path: Path, page_limit: int = DEFAULT_PAGE_LIMIT) -> dict[str, Any]:
    run = load_run(path)
    selection = json.loads((path / "selection.json").read_text(encoding="utf-8"))
    urls = selection.get("urls", [])
    if not urls:
        raise ValueError("No selection is saved. Use the report or the select command first.")
    if len(urls) > page_limit:
        raise ValueError(f"Selection has {len(urls)} pages; current limit is {page_limit}. Narrow it or pass --max-pages.")
    run["status"] = "collecting"
    run["message"] = f"Collecting {len(urls)} selected item(s)."
    save_run(path, run)
    if run["source_kind"] == "website":
        documents, evidence = asyncio.run(crawl_selected(path, urls, run))
    else:
        documents, evidence = collect_local(path, run)
    remove_shared_noise(documents, path)
    for doc in documents:
        if doc.get("prepared_path") and (path / doc["prepared_path"]).exists():
            text = (path / doc["prepared_path"]).read_text(encoding="utf-8")
            doc["content_sha256"] = digest(text.encode())
            doc["word_count"] = len(re.findall(r"\w+", text, re.UNICODE))
    update_manifests(path, documents, evidence)
    run["counts"] = counts(documents)
    run["status"] = "review" if run["counts"]["review"] else "ready"
    run["message"] = "Review items need the coding agent." if run["status"] == "review" else "The selected information is ready to package."
    run["events"].append({"at": now(), "stage": "collect", "message": run["message"]})
    save_run(path, run)
    return run


def prepare_agent(path: Path) -> Path:
    tasks = read_jsonl(path / "manifests" / "review_queue.jsonl")
    for task in tasks:
        task["instruction"] = "Inspect the evidence, preserve only supported information, and return include/exclude/review using the result schema."
    target = path / "agent" / "tasks.jsonl"
    write_jsonl(target, tasks)
    if not (path / "agent" / "results.jsonl").exists():
        atomic_text(path / "agent" / "results.jsonl", "")
    return target


def apply_agent(path: Path) -> dict[str, Any]:
    tasks = {row["task_id"]: row for row in read_jsonl(path / "agent" / "tasks.jsonl")}
    results = read_jsonl(path / "agent" / "results.jsonl")
    documents = read_jsonl(path / "manifests" / "documents.jsonl")
    by_id = {doc["document_id"]: doc for doc in documents}
    seen: set[str] = set()
    for result in results:
        task_id = result.get("task_id")
        if task_id not in tasks or task_id in seen:
            raise ValueError(f"Unknown or duplicate task: {task_id}")
        seen.add(task_id)
        task = tasks[task_id]
        doc = by_id[task["document_id"]]
        decision = result.get("decision", "review")
        confidence = float(result.get("confidence", 0))
        if result.get("status") == "completed" and decision == "include" and confidence >= .8:
            cleaned_input = str(result.get("cleaned_markdown", ""))
            first_h1 = re.search(r"(?m)^#\s+(.+)$", cleaned_input)
            if first_h1:
                doc["title"] = first_h1.group(1).strip()
            cleaned = basic_clean(cleaned_input, doc["title"])
            if len(re.findall(r"\w+", cleaned, re.UNICODE)) < 45:
                doc["lane"], doc["reasons"] = "needs_agent", ["Agent result is too fragmentary"]
                continue
            target = path / "prepared" / f"{doc['document_id']}.md"
            atomic_text(target, cleaned)
            doc["prepared_path"] = target.relative_to(path).as_posix()
            doc["content_sha256"] = digest(cleaned.encode())
            doc["word_count"] = len(re.findall(r"\w+", cleaned, re.UNICODE))
            doc["lane"] = "sensitive_review" if SENSITIVE_RE.search(cleaned) else "included"
            doc["reasons"] = ["Health-sensitive content remains in review"] if doc["lane"] == "sensitive_review" else []
        elif decision == "exclude":
            doc["lane"], doc["reasons"] = "excluded", [str(result.get("notes") or "Excluded by agent review")[:240]]
        else:
            doc["lane"], doc["reasons"] = "sensitive_review", [str(result.get("notes") or "Agent left this for review")[:240]]
    evidence = read_jsonl(path / "manifests" / "source_snapshot.jsonl")
    update_manifests(path, documents, evidence)
    run = load_run(path)
    run["counts"] = counts(documents)
    run["status"] = "review" if run["counts"]["review"] else "ready"
    run["message"] = "Agent results applied. Remaining review items stay outside the package."
    run["events"].append({"at": now(), "stage": "review", "message": run["message"]})
    save_run(path, run)
    return run


def validate_markdown(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    errors = []
    if len(re.findall(r"(?m)^#\s+", text)) != 1:
        errors.append(f"{path.name}: expected one H1")
    if len(re.findall(r"\w+", text, re.UNICODE)) < 45:
        errors.append(f"{path.name}: too little information")
    for pattern, label in ((RAW_HTML_RE, "raw HTML"), (IMAGE_MD_RE, "image syntax"), (CONTACT_RE, "contact detail"), (LOCAL_PATH_RE, "private path"), (URL_RE, "source URL"), (PROMO_RE, "promotion")):
        if pattern.search(text):
            errors.append(f"{path.name}: contains {label}")
    return errors


def package(path: Path) -> Path:
    run = load_run(path)
    documents = read_jsonl(path / "manifests" / "documents.jsonl")
    stage = path / f".package-{uuid.uuid4().hex}"
    articles = stage / "articles"
    articles.mkdir(parents=True)
    manifest, seen = [], set()
    for doc in documents:
        if doc["lane"] != "included":
            continue
        content = basic_clean((path / doc["prepared_path"]).read_text(encoding="utf-8"), doc["title"], public=True)
        content_hash = digest(content.encode())
        if content_hash in seen:
            continue
        seen.add(content_hash)
        filename = f"{portable_article_slug(doc['title'])}--{doc['public_id'][:8]}.md"
        atomic_text(articles / filename, content)
        manifest.append({
            "schema_version": "markdown-document-v1", "run_name": run["run_name"],
            "document_id": doc["public_id"], "title": doc["title"], "language": doc["language"],
            "path": f"articles/{filename}", "sha256": content_hash,
            "word_count": len(re.findall(r"\w+", content, re.UNICODE)),
        })
    write_jsonl(stage / "manifest.jsonl", manifest)
    if not manifest:
        shutil.rmtree(stage)
        raise ValueError("No ready documents are available to package. Resolve or exclude the review queue first.")
    atomic_json(stage / "package.json", {
        "schema_version": "markdown-package-v1", "profile": "markdown-knowledge-v1",
        "run_name": run["run_name"], "created_at": now(), "document_count": len(manifest),
        "compatibility": ["generic-rag", "knowledge-base", "vector-ingest"],
    })
    atomic_text(stage / "README.md", "# Clean Markdown knowledge package\n\nUse the Markdown files in `articles/`. Use `manifest.jsonl` for integrity and idempotency. Review-only material and source evidence are intentionally outside this folder.\n")
    errors = [error for row in manifest for error in validate_markdown(stage / row["path"])]
    if errors:
        raise ValueError("Package failed cleanup:\n- " + "\n- ".join(errors))
    target = path / "package"
    if target.exists():
        archived = path / f"package.previous-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"
        os.replace(target, archived)
    os.replace(stage, target)
    run["status"] = "packaged"
    run["message"] = f"Package built with {len(manifest)} knowledge document(s)."
    run["events"].append({"at": now(), "stage": "package", "message": run["message"]})
    save_run(path, run)
    return target


def validate(path: Path) -> dict[str, Any]:
    errors, warnings = [], []
    for item in read_jsonl(path / "manifests" / "source_snapshot.jsonl"):
        target = path / item["path"]
        if not target.exists() or digest(target.read_bytes()) != item["sha256"]:
            errors.append(f"Evidence changed or missing: {item['path']}")
    package_path = path / "package"
    manifest = read_jsonl(package_path / "manifest.jsonl")
    if not package_path.exists():
        errors.append("Package is missing")
    for item in manifest:
        target = package_path / item["path"]
        if not target.exists() or digest(target.read_bytes()) != item["sha256"]:
            errors.append(f"Package file changed or missing: {item['path']}")
        elif target.exists():
            errors.extend(validate_markdown(target))
    queue = read_jsonl(path / "manifests" / "review_queue.jsonl")
    if queue:
        warnings.append(f"{len(queue)} review item(s) remain outside the package")
    result = {"schema_version": "knowledge-intake-validation-v2", "healthy": not errors, "checked_at": now(), "errors": errors, "warnings": warnings}
    atomic_json(path / "reports" / "validation.json", result)
    run = load_run(path)
    run["status"] = "validated" if not errors else "failed"
    run["message"] = "The knowledge package passed validation." if not errors else f"Validation found {len(errors)} error(s)."
    save_run(path, run)
    return result


def public_state(path: Path, run: dict[str, Any] | None = None) -> dict[str, Any]:
    run = run or load_run(path)
    inventory = read_jsonl(path / "inventory.jsonl")
    grouped: dict[str, dict[str, Any]] = {}
    for row in inventory:
        group = grouped.setdefault(row["group"], {"name": row["group"], "count": 0, "selected": 0, "recommended": row["recommended"], "pages": []})
        group["count"] += 1
        group["selected"] += int(row["selected"])
        if len(group["pages"]) < 8:
            group["pages"].append({"url": row["url"], "label": row["label"], "selected": row["selected"], "recommended": row["recommended"]})
    documents = read_jsonl(path / "manifests" / "documents.jsonl")
    queue = read_jsonl(path / "manifests" / "review_queue.jsonl")
    return {
        "run_name": run["run_name"], "source": run["source"], "source_kind": run["source_kind"],
        "status": run["status"], "message": run["message"], "updated_at": run["updated_at"],
        "inventory_count": len(inventory), "selected_count": sum(row["selected"] for row in inventory),
        "groups": list(grouped.values()), "inventory": inventory, "counts": run["counts"],
        "review": queue[:50], "documents": [{"title": d["title"], "lane": d["lane"], "words": d["word_count"]} for d in documents[:100]],
        "events": run["events"][-20:], "package_ready": (path / "package").exists(),
    }


def render_report(path: Path) -> Path:
    assets = Path(__file__).resolve().parent.parent / "assets"
    template = assets / "report-template.html"
    font = assets / "fonts" / "barlow-condensed-latin.woff2"
    font_target = path / "fonts" / font.name
    font_target.parent.mkdir(parents=True, exist_ok=True)
    if not font_target.exists() or digest(font_target.read_bytes()) != digest(font.read_bytes()):
        shutil.copy2(font, font_target)
    target = path / "report.html"
    shutil.copy2(template, target)
    return target


def doctor() -> dict[str, Any]:
    try:
        import crawl4ai  # noqa: F401
        crawl = True
    except Exception:
        crawl = False
    try:
        import pypdf  # noqa: F401
        pdf = True
    except Exception:
        pdf = False
    return {
        "healthy": crawl and pdf, "checks": {"crawl4ai": crawl, "pdf_text": pdf, "workspace_writable": os.access(Path.cwd(), os.W_OK)},
        "setup": [] if crawl else ["uv sync --project <INTAKE_HOME>", "uv run --project <INTAKE_HOME> crawl4ai-setup"],
    }
