from __future__ import annotations

import hashlib
import mimetypes
import re
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Iterable
from urllib.parse import quote_plus, urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from PIL import Image

from config import DEFAULT_USER_AGENT, MEDIA_DIR, ensure_directories


IMAGE_PATTERN = re.compile(r"\.(?:jpg|jpeg|png|webp)(?:$|\?)", re.IGNORECASE)


@dataclass
class CandidateImage:
    source: str
    source_url: str


@dataclass
class DownloadedImage:
    source: str
    source_url: str
    local_path: str
    mime_type: str | None
    file_ext: str
    width_px: int | None
    height_px: int | None
    file_size_bytes: int
    status: str


def parse_direct_image_urls(raw_value: str) -> list[CandidateImage]:
    if not raw_value:
        return []
    direct_candidates: list[CandidateImage] = []
    page_candidates: list[CandidateImage] = []
    for chunk in split_reference_urls(raw_value):
        if is_probable_image_url(chunk) or is_yandex_disk_public_url(chunk):
            direct_candidates.append(CandidateImage(source="provided", source_url=chunk))
        elif chunk.startswith(("http://", "https://")):
            page_candidates.extend(extract_images_from_page(chunk, source="provided_page"))

    return direct_candidates + page_candidates


def collect_candidate_images(product: dict) -> list[CandidateImage]:
    candidates: list[CandidateImage] = []
    candidates.extend(parse_direct_image_urls(product.get("image_urls_raw", "")))

    product_url = product.get("product_url") or ""
    if product_url:
        for page_url in split_reference_urls(product_url):
            candidates.extend(extract_images_from_page(page_url, source="supplier_page"))

    supplier_site = product.get("supplier_site") or ""
    article = product.get("supplier_article") or product.get("article") or ""
    name = product.get("name") or ""
    if supplier_site and article:
        search_pages = search_web_pages(normalize_supplier_site(supplier_site), article, name)
        for page_url in search_pages:
            candidates.extend(extract_images_from_page(page_url, source="search_page"))

    if not candidates and article:
        search_pages = search_web_pages("", article, name)
        for page_url in search_pages:
            candidates.extend(extract_images_from_page(page_url, source="internet_page"))

    return deduplicate_candidates(candidates)


def deduplicate_candidates(candidates: Iterable[CandidateImage]) -> list[CandidateImage]:
    unique: list[CandidateImage] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = candidate.source_url.strip()
        if not key or key in seen:
            continue
        seen.add(key)
        unique.append(candidate)
    return unique


def search_web_pages(supplier_site: str, article: str, name: str, limit: int = 3) -> list[str]:
    query_parts = [article]
    if name:
        query_parts.append(name)
    if supplier_site:
        query_parts.append(f"site:{supplier_site}")
    query = " ".join(query_parts)
    url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"

    try:
        response = requests.get(url, headers=request_headers(), timeout=20)
        response.raise_for_status()
    except requests.RequestException:
        return []

    soup = BeautifulSoup(response.text, "html.parser")
    links: list[str] = []
    for anchor in soup.select("a.result__a"):
        href = anchor.get("href")
        if href and href.startswith("http"):
            links.append(href)
        if len(links) >= limit:
            break
    return links


def split_reference_urls(raw_value: str) -> list[str]:
    chunks = [chunk.strip() for chunk in re.split(r"[;\s,]+", raw_value) if chunk.strip()]
    return [chunk for chunk in chunks if chunk.startswith(("http://", "https://"))]


def normalize_supplier_site(raw_value: str) -> str:
    value = raw_value.strip()
    if not value:
        return ""
    parsed = urlparse(value if "://" in value else f"https://{value}")
    return parsed.netloc or value


def is_probable_image_url(url: str) -> bool:
    return bool(IMAGE_PATTERN.search(url))


def is_yandex_disk_public_url(url: str) -> bool:
    host = (urlparse(url).netloc or "").lower()
    return "disk.yandex" in host or "yadi.sk" in host


def extract_images_from_page(url: str, source: str) -> list[CandidateImage]:
    try:
        response = requests.get(url, headers=request_headers(), timeout=20)
        response.raise_for_status()
    except requests.RequestException:
        return []

    soup = BeautifulSoup(response.text, "html.parser")
    candidates: list[CandidateImage] = []

    meta_image = soup.find("meta", attrs={"property": "og:image"})
    if meta_image and meta_image.get("content"):
        candidates.append(
            CandidateImage(source=source, source_url=urljoin(url, meta_image["content"]))
        )

    for image in soup.find_all("img"):
        raw_url = image.get("src") or image.get("data-src") or image.get("data-original")
        if not raw_url:
            continue
        absolute_url = urljoin(url, raw_url)
        if IMAGE_PATTERN.search(absolute_url):
            candidates.append(CandidateImage(source=source, source_url=absolute_url))

    return candidates


def download_candidate_images(product_id: int, candidates: list[CandidateImage], limit: int = 10) -> list[DownloadedImage]:
    ensure_directories()
    product_dir = MEDIA_DIR / str(product_id)
    product_dir.mkdir(parents=True, exist_ok=True)

    downloaded: list[DownloadedImage] = []
    for index, candidate in enumerate(candidates[:limit], start=1):
        try:
            downloaded.append(download_image(product_dir, candidate, index))
        except requests.RequestException:
            continue
        except OSError:
            continue
    return downloaded


def download_image(product_dir: Path, candidate: CandidateImage, index: int) -> DownloadedImage:
    download_url = resolve_download_url(candidate.source_url)
    response = requests.get(download_url, headers=request_headers(), timeout=30)
    response.raise_for_status()
    content_type = response.headers.get("Content-Type")
    content = response.content

    extension = infer_extension(candidate.source_url, content_type, content)
    file_hash = hashlib.md5(content).hexdigest()[:12]
    file_name = f"{index:02d}_{file_hash}.{extension}"
    file_path = product_dir / file_name
    file_path.write_bytes(content)

    width_px: int | None = None
    height_px: int | None = None
    try:
        with Image.open(file_path) as image:
            width_px, height_px = image.size
    except OSError:
        pass

    return DownloadedImage(
        source=candidate.source,
        source_url=candidate.source_url,
        local_path=str(file_path),
        mime_type=content_type,
        file_ext=extension,
        width_px=width_px,
        height_px=height_px,
        file_size_bytes=len(content),
        status="active",
    )


def infer_extension(source_url: str, content_type: str | None, content: bytes) -> str:
    parsed = Path(urlparse(source_url).path).suffix.lower().lstrip(".")
    if parsed in {"jpg", "jpeg", "png", "webp"}:
        return parsed

    if content_type:
        guessed = mimetypes.guess_extension(content_type.split(";")[0].strip())
        if guessed:
            normalized = guessed.lstrip(".")
            if normalized == "jpe":
                return "jpg"
            return normalized

    try:
        with Image.open(BytesIO(content)) as image:
            detected = (image.format or "").lower()
            if detected == "jpeg":
                return "jpg"
            if detected:
                return detected
    except OSError:
        pass
    return "jpg"


def resolve_download_url(url: str) -> str:
    if not is_yandex_disk_public_url(url):
        return url

    try:
        response = requests.get(
            "https://cloud-api.yandex.net/v1/disk/public/resources/download",
            params={"public_key": url},
            headers=request_headers(),
            timeout=20,
        )
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError):
        return url

    href = payload.get("href")
    return href if isinstance(href, str) and href else url


def request_headers() -> dict[str, str]:
    return {
        "User-Agent": DEFAULT_USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/*;q=0.8,*/*;q=0.7",
        "Accept-Language": "ru,en;q=0.9",
    }
