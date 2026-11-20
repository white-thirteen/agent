"""Linux Docker compatibility gate; never modifies the protected running container.

Run on the authorized VM as a Docker-capable user. This first gate records exact
package/build/load evidence. A successful load alone is NOT full Task acceptance:
Chinese/filter/transaction/snapshot/restart checks must also be recorded.
"""

import argparse
import hashlib
import json
import shutil
import subprocess
import tempfile
import time
import urllib.request
import uuid
from pathlib import Path

BASE = (
    "postgres:17.6-bookworm@sha256:f3bd19c606e442c3d7bdfa8002e03fe260a1023351e0ea4598032022b68dd6e3"
)
PACKAGE = "postgresql-17-pg-search_0.26.6-1PARADEDB-bookworm_amd64.deb"
URL = "https://github.com/paradedb/paradedb/releases/download/v0.26.6/" + PACKAGE
SHA256 = "16a14d382f088bc23e7c8624e4860fd8bf01a939c67c7695348de0615e323ddb"
PROTECTED = "agent-engine-demo-db-postgres-1"


def command(*args, input=None):
    result = subprocess.run(args, input=input, text=True, capture_output=True, check=False)
    return {
        "command": list(args),
        "exit_code": result.returncode,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--package", type=Path, help="Optional already downloaded official package")
    args = parser.parse_args()
    token = uuid.uuid4().hex[:12]
    image = "codex-v201111:" + token
    container = "codex-v201111-" + token
    volume = "codex-v201111-data-" + token
    workspace = Path(tempfile.mkdtemp(prefix="codex-v201111-"))
    evidence = {
        "token": token,
        "status": "BLOCKED",
        "package_url": URL,
        "expected_sha256": SHA256,
        "commands": [],
        "semantic_checks": "not_executed",
    }

    def record(*items, input=None):
        result = command(*items, input=input)
        evidence["commands"].append(result)
        return result

    def require(*items, input=None):
        result = record(*items, input=input)
        if result["exit_code"]:
            raise RuntimeError("Command failed: " + " ".join(items[:3]))
        return result["stdout"]

    def protected():
        # Config.Env is intentionally excluded: it contains the existing password.
        state = require(
            "docker",
            "inspect",
            "--format",
            "{{.Id}}|{{.State.StartedAt}}|{{.Config.Image}}|{{json .Mounts}}",
            PROTECTED,
        )
        packages = require(
            "docker",
            "exec",
            PROTECTED,
            "dpkg-query",
            "-W",
            "postgresql-17",
            "postgresql-client-17",
            "postgresql-17-pgvector",
        )
        databases = {}
        for database in ("agent_demo", "agent_demo_test"):
            prefix = (
                "docker",
                "exec",
                PROTECTED,
                "psql",
                "-X",
                "-U",
                "agent_bootstrap",
                "-d",
                database,
                "-At",
                "-v",
                "ON_ERROR_STOP=1",
                "-c",
            )
            tables = require(
                *prefix,
                "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename",
            ).splitlines()
            rows = {}
            for table in tables:
                quoted = '"' + table.replace('"', '""') + '"'
                # Raw rows remain in process memory only; evidence contains digests.
                result = command(
                    *prefix,
                    "SELECT row_to_json(t)::text FROM public."
                    + quoted
                    + " t ORDER BY row_to_json(t)::text",
                )
                if result["exit_code"]:
                    raise RuntimeError("Protected row fingerprint failed")
                rows[table] = hashlib.sha256(result["stdout"].encode()).hexdigest()
            schema = require(
                *prefix,
                "SELECT c.relname,a.attnum,a.attname,"
                "format_type(a.atttypid,a.atttypmod),a.attnotnull,"
                "coalesce(pg_get_expr(d.adbin,d.adrelid),'') "
                "FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                "JOIN pg_attribute a ON a.attrelid=c.oid "
                "LEFT JOIN pg_attrdef d ON d.adrelid=c.oid AND d.adnum=a.attnum "
                "WHERE n.nspname='public' AND c.relkind IN ('r','p') "
                "AND a.attnum>0 AND NOT a.attisdropped ORDER BY c.relname,a.attnum",
            )
            databases[database] = {
                "rows_sha256": rows,
                "columns_sha256": hashlib.sha256(schema.encode()).hexdigest(),
            }
        return {"container": state, "packages": packages, "databases": databases}

    try:
        evidence["protected_before"] = protected()
        target = workspace / PACKAGE
        if args.package:
            shutil.copyfile(args.package, target)
        else:
            with urllib.request.urlopen(URL, timeout=120) as response, target.open("wb") as out:
                shutil.copyfileobj(response, out)
        evidence["actual_sha256"] = hashlib.sha256(target.read_bytes()).hexdigest()
        evidence["package_bytes"] = target.stat().st_size
        if evidence["actual_sha256"] != SHA256:
            raise RuntimeError("Official package SHA256 mismatch")
        require("dpkg-deb", "-f", str(target), "Package", "Version", "Architecture", "Depends")
        dockerfile = f"""FROM {BASE}
COPY {PACKAGE} /tmp/pg_search.deb
RUN apt-get update && apt-get install -y --no-remove --no-install-recommends \\
    postgresql-17=17.6-2.pgdg12+1 postgresql-client-17=17.6-2.pgdg12+1 \\
    postgresql-17-pgvector=0.8.7-1.pgdg12+1 /tmp/pg_search.deb \\
    && test \"$(pg_config --version)\" = 'PostgreSQL 17.6 (Debian 17.6-2.pgdg12+1)' \\
    && test \"$(dpkg-query -W -f='${{Version}}' postgresql-17-pgvector)\" = '0.8.7-1.pgdg12+1' \\
    && rm -rf /var/lib/apt/lists/* /tmp/pg_search.deb
"""
        (workspace / "Dockerfile").write_text(dockerfile)
        # Legacy build keeps cache as image layers; removing the resulting image
        # also removes its untagged parents. Avoid a shared BuildKit cache/prune.
        require(
            "env",
            "DOCKER_BUILDKIT=0",
            "docker",
            "build",
            "--label",
            "codex.v201111=" + token,
            "-t",
            image,
            str(workspace),
        )
        require(
            "docker",
            "run",
            "--rm",
            image,
            "sh",
            "-c",
            "pg_config --version; dpkg-query -W postgresql-17 postgresql-client-17 "
            "postgresql-17-pgvector postgresql-17-pg-search libopenblas0; "
            "ldd /usr/lib/postgresql/17/lib/pg_search.so",
        )
        require("docker", "volume", "create", "--label", "codex.v201111=" + token, volume)
        # No host port; trust is confined to an isolated, otherwise unreachable container.
        require(
            "docker",
            "run",
            "-d",
            "--name",
            container,
            "--network",
            "none",
            "--label",
            "codex.v201111=" + token,
            "-e",
            "POSTGRES_HOST_AUTH_METHOD=trust",
            "--mount",
            f"type=volume,source={volume},target=/var/lib/postgresql/data",
            image,
            "-c",
            "shared_preload_libraries=pg_search",
        )
        for _ in range(30):
            ready = command("docker", "exec", container, "pg_isready", "-U", "postgres")
            if ready["exit_code"] == 0:
                break
            time.sleep(1)
        else:
            record("docker", "logs", container)
            raise RuntimeError("Exact-version PostgreSQL with preload did not start")
        require(
            "docker",
            "exec",
            "-i",
            container,
            "psql",
            "-X",
            "-U",
            "postgres",
            "-v",
            "ON_ERROR_STOP=1",
            "-At",
            input="CREATE EXTENSION vector;\n"
            "CREATE EXTENSION pg_search;\nSHOW server_version;\n"
            "SELECT extname,extversion FROM pg_extension ORDER BY extname;\n",
        )
        evidence["status"] = "LOAD_PASSED_SEMANTICS_PENDING"
    except (RuntimeError, OSError) as error:
        evidence["failure"] = str(error)
    finally:
        # Delete only exact resources generated in this invocation; no broad prune.
        for resource_args in [
            ("rm", "-f", container),
            ("volume", "rm", volume),
            ("image", "rm", image),
        ]:
            record("docker", *resource_args)
        remaining = []
        for resource_args in [("ps", "-aq"), ("volume", "ls", "-q"), ("image", "ls", "-q")]:
            result = record("docker", *resource_args, "--filter", "label=codex.v201111=" + token)
            if result["exit_code"] or result["stdout"]:
                remaining.append(result)
        evidence["cleanup_complete"] = not remaining
        evidence["protected_after"] = protected()
        evidence["protected_unchanged"] = (
            evidence.get("protected_before") == evidence["protected_after"]
        )
        shutil.rmtree(workspace)
        evidence["workspace_removed"] = not workspace.exists()
        args.output.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({k: v for k, v in evidence.items() if k != "commands"}, ensure_ascii=False))
    return (
        0
        if (
            evidence["status"] == "LOAD_PASSED_SEMANTICS_PENDING"
            and evidence["protected_unchanged"]
            and evidence["cleanup_complete"]
        )
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
