"""Run the existing synthetic semantic probe in a new isolated container.

The image must already exist; this script never builds, pulls, or accesses the
formal database. Functional results do not establish extension build safety.
"""

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path

from verify_v2_01_compatibility import semantics

LIB_SHA = "e3b19a5d350efc27d3c9b23587f68004eee5d2468b96dc88422b73ad4432a598"


def child(container):
    calls = []

    def require(*command, input=None):
        result = subprocess.run(command, input=input, text=True, capture_output=True, timeout=60)
        calls.append(
            dict(
                command=command,
                exit_code=result.returncode,
                stdout=result.stdout.strip(),
                stderr=result.stderr.strip(),
            )
        )
        if result.returncode:
            raise RuntimeError("semantic command failed")
        return result.stdout.strip()

    result = {"calls": calls}
    try:
        result["checks"] = semantics(require, container)
        result["status"] = "PASSED"
    except Exception as error:
        result.update(status="FAILED", failure=repr(error))
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["status"] == "PASSED" else 1


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--child")
    parser.add_argument("--image")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--minimum-free-bytes", type=int)
    args = parser.parse_args()
    if args.child:
        return child(args.child)
    if (
        not args.image
        or not re.fullmatch(r"sha256:[0-9a-f]{64}", args.image)
        or not args.output
        or not args.minimum_free_bytes
        or args.minimum_free_bytes < 1
    ):
        parser.error("exact image ID, output and positive disk budget required")
    token = uuid.uuid4().hex[:12]
    container, volume = "codex-v201sem-" + token, "codex-v201sem-data-" + token
    evidence = {
        "status": "BLOCKED",
        "token": token,
        "image": args.image,
        "commands": [],
        "source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "semantics_source_sha256": hashlib.sha256(
            Path(semantics.__code__.co_filename).read_bytes()
        ).hexdigest(),
        "build_safety": "NOT_VERIFIED",
    }

    def run(*command, input=None, timeout=60, check=True):
        result = subprocess.run(
            command, input=input, text=True, capture_output=True, timeout=timeout
        )
        evidence["commands"].append(
            dict(
                command=command,
                exit_code=result.returncode,
                stdout=result.stdout.strip(),
                stderr=result.stderr.strip(),
            )
        )
        if check and result.returncode:
            raise RuntimeError("command failed: " + " ".join(command[:3]))
        return result

    # Reserve the receipt before creating resources, so old evidence is immutable.
    try:
        receipt = args.output.open("x", encoding="utf-8")
    except FileExistsError:
        parser.error("output already exists")
    try:
        free = shutil.disk_usage("/var/lib/docker").free
        evidence.update(free_bytes=free, minimum_free_bytes=args.minimum_free_bytes)
        if free < args.minimum_free_bytes:
            raise RuntimeError("insufficient Docker filesystem space")
        actual = run(
            "docker",
            "image",
            "inspect",
            "--format",
            "{{.Id}}|{{.Os}}|{{.Architecture}}",
            args.image,
        ).stdout.strip()
        if actual != args.image + "|linux|amd64":
            raise RuntimeError("image identity or platform mismatch")
        run("docker", "volume", "create", "--label", "codex.v201sem=" + token, volume)
        run(
            "docker",
            "create",
            "--name",
            container,
            "--network",
            "none",
            "--memory",
            "768m",
            "--cpus",
            "1",
            "--pids-limit",
            "128",
            "--label",
            "codex.v201sem=" + token,
            "-e",
            "POSTGRES_HOST_AUTH_METHOD=trust",
            "-e",
            "OPENBLAS_NUM_THREADS=1",
            "-e",
            "OMP_NUM_THREADS=1",
            "--mount",
            "type=volume,source=" + volume + ",target=/var/lib/postgresql/data",
            args.image,
            "-c",
            "shared_preload_libraries=pg_search",
        )
        run("docker", "start", container)
        for _ in range(60):
            if (
                run(
                    "docker", "exec", container, "pg_isready", "-U", "postgres", check=False
                ).returncode
                == 0
            ):
                break
            time.sleep(1)
        else:
            raise RuntimeError("isolated server did not become ready")
        versions = run(
            "docker",
            "exec",
            container,
            "dpkg-query",
            "-W",
            "-f=${Package}=${Version}\n",
            "postgresql-17",
            "postgresql-client-17",
            "postgresql-17-pgvector",
            "postgresql-17-pg-search",
        ).stdout.splitlines()
        expected = {
            "postgresql-17=17.12-1.pgdg12+1",
            "postgresql-client-17=17.12-1.pgdg12+1",
            "postgresql-17-pgvector=0.8.7-1.pgdg12+2",
            "postgresql-17-pg-search=0.26.6",
        }
        if set(versions) != expected:
            raise RuntimeError("candidate package versions differ")
        library = run(
            "docker", "exec", container, "sha256sum", "/usr/lib/postgresql/17/lib/pg_search.so"
        ).stdout.split()[0]
        if library != LIB_SHA:
            raise RuntimeError("candidate extension binary differs")
        sql = (
            "CREATE EXTENSION vector; CREATE EXTENSION pg_search; "
            "SELECT current_setting('server_version_num'); "
            "SELECT extname||'='||extversion FROM pg_extension ORDER BY extname;"
        )
        versions = run(
            "docker",
            "exec",
            "-i",
            container,
            "psql",
            "-X",
            "-q",
            "-U",
            "postgres",
            "-v",
            "ON_ERROR_STOP=1",
            "-At",
            input=sql,
        ).stdout.splitlines()
        if versions != ["170012", "pg_search=0.26.6", "plpgsql=1.0", "vector=0.8.7"]:
            raise RuntimeError("runtime versions differ")
        result = run(
            sys.executable,
            str(Path(__file__).resolve()),
            "--child",
            container,
            timeout=240,
            check=False,
        )
        evidence["semantics"] = json.loads(result.stdout)
        if result.returncode:
            raise RuntimeError("semantic probe failed")
        evidence["status"] = "FUNCTIONAL_PASSED_SAFETY_UNVERIFIED"
    except (OSError, RuntimeError, subprocess.TimeoutExpired, ValueError) as error:
        evidence["failure"] = repr(error)
    finally:
        # A create command can time out after Docker created the resource. Find
        # only this invocation's label, including resources whose call timed out.
        for kind, remove in (
            (("ps", "-aq"), ("rm", "-f")),
            (("volume", "ls", "-q"), ("volume", "rm")),
        ):
            found = run("docker", *kind, "--filter", "label=codex.v201sem=" + token, check=False)
            if found.returncode == 0:
                for resource in found.stdout.splitlines():
                    run("docker", *remove, resource, check=False)
        remains = [
            run("docker", *kind, "--filter", "label=codex.v201sem=" + token, check=False)
            for kind in (("ps", "-aq"), ("volume", "ls", "-q"))
        ]
        evidence["cleanup_complete"] = all(
            r.returncode == 0 and not r.stdout.strip() for r in remains
        )
        with receipt:
            receipt.write(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n")
    return (
        0
        if evidence["status"] == "FUNCTIONAL_PASSED_SAFETY_UNVERIFIED"
        and evidence["cleanup_complete"]
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
