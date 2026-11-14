"""Explicit immutable Qwen download; optional official Qwen mirror verifies HF weight SHA256."""

import argparse
import hashlib
from pathlib import Path
from urllib.request import urlopen


def main():
    from huggingface_hub import HfApi, snapshot_download

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--download", action="store_true", required=True)
    parser.add_argument(
        "--modelscope-mirror",
        action="store_true",
        help="Use Qwen's official ModelScope weight mirror; verify HF checksum",
    )
    args = parser.parse_args()
    # This explicit network operation also prepares the fixed context tokenizer cache.
    import tiktoken

    tiktoken.get_encoding("cl100k_base")
    path = Path("D:/AI/models/qwen3-embedding-0.6b")
    info = HfApi().model_info("Qwen/Qwen3-Embedding-0.6B", files_metadata=True)
    revision = info.sha
    snapshot_download(
        "Qwen/Qwen3-Embedding-0.6B",
        revision=revision,
        local_dir=path,
        allow_patterns=["*.json", "*.txt", "*.model", "README.md", "1_Pooling/*"]
        + ([] if args.modelscope_mirror else ["*.safetensors"]),
        max_workers=1,
    )
    weight = next(item for item in info.siblings if item.rfilename == "model.safetensors")
    target = path / "model.safetensors"
    if args.modelscope_mirror and not target.exists():
        partial = path / "model.safetensors.partial"
        with (
            urlopen(
                "https://www.modelscope.cn/models/Qwen/Qwen3-Embedding-0.6B/resolve/master/model.safetensors",
                timeout=120,
            ) as response,
            partial.open("wb") as output,
        ):
            while block := response.read(1024 * 1024):
                output.write(block)
        with partial.open("rb") as source:
            if hashlib.file_digest(source, "sha256").hexdigest() != weight.lfs.sha256:
                raise ValueError("ModelScope weight differs from immutable HF revision")
        partial.replace(target)
    with target.open("rb") as source:
        checksum = hashlib.file_digest(source, "sha256").hexdigest()
    if checksum != weight.lfs.sha256:
        raise ValueError("Local weight differs from immutable HF revision")
    (path / "REVISION").write_text(revision, encoding="utf-8")
    print(f"Local Qwen cache ready, revision={revision}, weight_sha256={checksum}")


if __name__ == "__main__":
    main()
