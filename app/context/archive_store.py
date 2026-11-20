"""Deterministic, bounded storage of public history in local Markdown files."""

import hashlib
import json
import os
import tempfile
from pathlib import Path

from app.context.models import PublicMessage, SessionIdentity


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def make_segment(identity, checkpoint_id, messages):
    ids = [message.message_id for message in messages]
    if not ids or any(not value for value in ids) or len(set(ids)) != len(ids):
        raise ValueError("Archive requires unique message IDs")
    segment_id = digest(canonical(ids))
    payload = {
        "version": 1,
        "archive_ref": identity.archive_ref(segment_id),
        "user_id": identity.user_id,
        "conversation_id": identity.conversation_id,
        "source_checkpoint_id": checkpoint_id,
        "message_ids": ids,
        "message_count": len(ids),
        "messages": [m.model_dump() for m in messages],
    }
    content_hash = digest(canonical(payload["messages"]))
    return segment_id, content_hash, payload


class ArchiveStore:
    def __init__(self, root: Path):
        self.root = Path(root).resolve()

    def relative_path(self, identity: SessionIdentity, segment_id: str) -> str:
        owner = digest(canonical([identity.user_id, identity.conversation_id]))
        return f"{owner}/{segment_id}.md"

    def _path(self, relative_path: str) -> Path:
        path = (self.root / relative_path).resolve()
        if not path.is_relative_to(self.root) or path == self.root:
            raise ValueError("Archive path escapes root")
        return path

    def encode(self, payload):
        # JSON escapes newlines, so body content cannot create a Markdown fence or
        # metadata line. UTF-8 text remains visible and decodes losslessly.
        return b"# Context archive v1\n\n```json\n" + canonical(payload) + b"\n```\n"

    def publish(self, relative_path, data):
        path = self._path(relative_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(prefix=".archive-", suffix=".tmp", dir=path.parent)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            try:
                os.link(name, path)  # Atomic no-replace publication, including concurrent retries.
            except FileExistsError:
                if path.read_bytes() != data:
                    raise ValueError("Archive file conflict") from None
        finally:
            os.unlink(name)
        return digest(data)

    def read(self, archive, max_bytes):
        expected_path = self.relative_path(archive.identity, archive.segment_id)
        if archive.relative_path != expected_path or archive.status != "READY":
            raise ValueError("Invalid archive metadata")
        path = self._path(archive.relative_path)
        with path.open("rb") as stream:
            data = stream.read(max_bytes + 1)
        if len(data) > max_bytes:
            raise ValueError("Archive exceeds read budget")
        if digest(data) != archive.file_hash:
            raise ValueError("Archive integrity failure")
        prefix, suffix = b"# Context archive v1\n\n```json\n", b"\n```\n"
        if not data.startswith(prefix) or not data.endswith(suffix):
            raise ValueError("Invalid archive format")
        payload = json.loads(data[len(prefix) : -len(suffix)])
        messages = tuple(PublicMessage.model_validate(m) for m in payload["messages"])
        segment, content_hash, expected = make_segment(
            archive.identity, archive.source_checkpoint_id, messages
        )
        if (
            payload != expected
            or segment != archive.segment_id
            or content_hash != archive.content_hash
            or tuple(payload["message_ids"]) != archive.message_ids
            or payload["archive_ref"] != archive.archive_ref
        ):
            raise ValueError("Archive metadata mismatch")
        return messages
