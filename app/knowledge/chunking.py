"""Bounded UTF-8 source parsing with exact source lines and Unicode-safe splitting."""

import hashlib
import json
import os
import re
import tempfile
from functools import lru_cache
from pathlib import Path

import tiktoken

from app.knowledge.models import Chunk, Document, KnowledgeError, ManifestEntry, canonical, digest

CONTEXT_TOKENIZER_URL = "https://openaipublic.blob.core.windows.net/encodings/cl100k_base.tiktoken"
CONTEXT_TOKENIZER_SHA256 = "223921b76ee99bde995b7ff738513eef100fb51d18c93597a113bcffe865b2a7"


@lru_cache(maxsize=1)
def context_tokenizer():
    """Require tiktoken's verified local cache; network is exclusive to explicit download.

    Cache resolution follows the installed tiktoken 0.14 load.read_file_cached contract.
    Lazy loading keeps disabled knowledge resources independent of tokenizer assets.
    """
    cache_directory = os.environ.get(
        "TIKTOKEN_CACHE_DIR",
        os.environ.get("DATA_GYM_CACHE_DIR", str(Path(tempfile.gettempdir()) / "data-gym-cache")),
    )
    cache_key = hashlib.sha1(CONTEXT_TOKENIZER_URL.encode()).hexdigest()
    path = Path(cache_directory) / cache_key
    if (
        not cache_directory
        or not path.is_file()
        or hashlib.sha256(path.read_bytes()).hexdigest() != CONTEXT_TOKENIZER_SHA256
    ):
        raise KnowledgeError("knowledge_tokenizer_unavailable")
    return tiktoken.get_encoding("cl100k_base")


def token_count(text: str) -> int:
    return len(context_tokenizer().encode(text, disallowed_special=()))


def read_manifest(root: Path, manifest: Path) -> list[ManifestEntry]:
    entries = [
        ManifestEntry.model_validate(item) for item in json.loads(manifest.read_text("utf-8"))
    ]
    if not 1 <= len(entries) <= 50:
        raise ValueError("Manifest must contain 1..50 documents")
    if len({e.document_id for e in entries}) != len(entries):
        raise ValueError("Duplicate document ID")
    for entry in entries:
        source_path(root, entry.filename)
    return entries


def source_path(root: Path, filename: str) -> Path:
    relative = Path(filename)
    path = (root / relative).resolve()
    if relative.is_absolute() or not path.is_relative_to(root.resolve()):
        raise ValueError("Source must remain inside the controlled knowledge root")
    if path.suffix.lower() not in (".md", ".txt") or not path.is_file():
        raise ValueError("Only existing local md/txt sources are accepted")
    if path.stat().st_size > 256 * 1024:
        raise ValueError("Knowledge source exceeds 256 KiB")
    return path


def prepare_document(root: Path, entry: ManifestEntry, profile: str) -> Document:
    text = (
        source_path(root, entry.filename)
        .read_text("utf-8-sig")
        .replace("\r\n", "\n")
        .replace("\r", "\n")
    )
    if not text.strip():
        raise ValueError("Empty source cannot replace a document")
    version = digest(
        canonical(
            {
                "text": text,
                "metadata": entry.model_dump(),
                "parser": "parser-v1",
                "chunker": "chunker-v1",
                "profile": profile,
            }
        )
    )
    chunks = []
    headings = []
    pending = []
    start = 1
    section = None

    def emit():
        if not pending:
            return
        body = "\n".join(pending)
        # Character boundaries preserve Unicode; line attribution follows original newlines.
        offset = 0
        while offset < len(body):
            lo, hi = offset + 1, len(body)
            while lo < hi:
                middle = (lo + hi + 1) // 2
                if token_count(body[offset:middle]) <= 500:
                    lo = middle
                else:
                    hi = middle - 1
            end = lo
            content = body[offset:end]
            prefix = entry.source_title + (" / " + section if section else "")
            embedding_text = prefix + "\n" + content
            if token_count(embedding_text) > 700:
                raise ValueError("Source heading exceeds embedding text budget")
            ordinal = len(chunks)
            content_hash = digest(content)
            chunks.append(
                Chunk(
                    chunk_id=digest(canonical([entry.document_id, version, ordinal, content_hash])),
                    document_id=entry.document_id,
                    document_version=version,
                    ordinal=ordinal,
                    section=section,
                    line_start=start + body[:offset].count("\n"),
                    line_end=start + body[:end].count("\n") - int(content.endswith("\n")),
                    content=content,
                    content_hash=content_hash,
                    token_count=token_count(content),
                    embedding_text=embedding_text,
                )
            )
            offset = end
        pending.clear()

    for line_number, line in enumerate(text.split("\n"), 1):
        is_heading = entry.filename.lower().endswith(".md") and re.match(r"^#{1,6}\s+", line)
        if not line.strip() or is_heading:
            emit()
        if is_heading:
            level = len(line) - len(line.lstrip("#"))
            headings[:] = [(depth, title) for depth, title in headings if depth < level]
            headings.append((level, line.lstrip("#").strip()))
            section = " / ".join(title for _, title in headings)
        elif line.strip():
            if not pending:
                start = line_number
            pending.append(line)
    emit()
    if not chunks:
        raise ValueError("Source has no body content")
    return Document(
        entry=entry,
        document_version=version,
        content_hash=digest(text),
        embedding_profile=profile,
        chunks=tuple(chunks),
    )
