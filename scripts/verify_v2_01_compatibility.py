"""Linux Docker compatibility gate; never modifies the protected running container.

Run on the authorized VM as a Docker-capable user. Package/build/load evidence
precedes Chinese/filter/transaction/snapshot/restart checks. --load-only explicitly
leaves semantic checks pending and must not be interpreted as full acceptance.
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
from datetime import UTC, datetime
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


def semantics(require, container):
    """Synthetic 1024-D fixtures exercise DB behavior, not Qwen retrieval quality."""
    prefix = (
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
    )

    def sql(text):
        return require(*prefix, input=text)

    def matching(query="退款", domain="platform_help"):
        # Inputs here are controlled fixture constants. PREPARE below separately
        # exercises typed query/domain/limit parameters using the same predicate.
        return (
            "SELECT c.chunk_id FROM probe_chunks c JOIN probe_documents d "
            "ON c.document_id=d.document_id AND c.document_version=d.document_version "
            "WHERE d.domain='" + domain + "' AND c.chunk_id @@@ paradedb.match("
            "'search_text','" + query + "',tokenizer => "
            '\'{"type":"jieba","search_mode":true}\'::jsonb) '
            "ORDER BY paradedb.score(c.chunk_id) DESC,c.chunk_id LIMIT 1"
        )

    sql("""
CREATE TABLE probe_documents(document_id text PRIMARY KEY, document_version text, domain text);
CREATE TABLE probe_chunks(chunk_id text PRIMARY KEY,document_id text,document_version text,
                          search_text text,embedding vector(1024));
INSERT INTO probe_documents VALUES ('target-doc','v1','platform_help'),
    ('deny-doc','v1','after_sales_help'),('stale-doc','v2','platform_help');
INSERT INTO probe_chunks VALUES
    ('target-text-id','target-doc','v1','帮助 / 退款说明\n申请模拟退款，dev-user必须等待审批。'
        || repeat('背景资料 ',100),
       ('[1,' || repeat('0,',1022) || '0]')::vector),
    ('stale-text-id','stale-doc','v1','退款',('[1,' || repeat('0,',1022) || '0]')::vector);
INSERT INTO probe_chunks
    SELECT 'deny-' || n,'deny-doc','v1','退款',
           ('[1,' || repeat('0,',1022) || '0]')::vector FROM generate_series(1,15) n;
CREATE INDEX probe_sparse ON probe_chunks USING paradedb
    (chunk_id,(search_text::pdb.jieba('search_mode=true')));
""")
    checks = {}
    tokens = sql("SELECT array_to_json('南京市长江大桥'::pdb.jieba('search_mode=true')::text[])")
    checks["jieba_tokens"] = json.loads(tokens)
    assert {"南京市", "长江大桥"} <= set(checks["jieba_tokens"]), "Jieba compounds missing"
    assert sql(matching()) == "target-text-id", "Filter/current-version before top K failed"
    assert sql(matching("dev-user")) == "target-text-id", "English identifier failed"
    checks["text_id_chinese_english_domain_current_version_topk"] = True
    unfiltered = sql(
        "SELECT chunk_id FROM probe_chunks WHERE chunk_id @@@ "
        "paradedb.match('search_text','退款') "
        "ORDER BY paradedb.score(chunk_id) DESC,chunk_id LIMIT 1"
    )
    assert unfiltered != "target-text-id", "Fixture does not exercise pre-topk filtering"
    checks["unfiltered_top1"] = unfiltered
    parameterized = sql("""
PREPARE sparse_probe(text,text,int) AS
SELECT c.chunk_id FROM probe_chunks c JOIN probe_documents d
ON c.document_id=d.document_id AND c.document_version=d.document_version
WHERE d.domain=$2 AND c.chunk_id @@@ paradedb.match('search_text',$1,
    tokenizer => '{"type":"jieba","search_mode":true}'::jsonb)
ORDER BY paradedb.score(c.chunk_id) DESC,c.chunk_id LIMIT $3;
EXECUTE sparse_probe('退款','platform_help',1);
EXECUTE sparse_probe('退款','missing-domain',1);
DEALLOCATE sparse_probe;
""")
    assert parameterized == "target-text-id", "Prepared query/domain/limit parameters failed"
    checks["prepared_parameters"] = True
    # An uncommitted replacement is searchable in its own transaction, then
    # disappears on rollback, with the previous source/vector pair intact.
    replaced = sql(
        "BEGIN; UPDATE probe_chunks SET search_text='回滚探针' "
        "WHERE chunk_id='target-text-id';\n" + matching("回滚探针") + ";ROLLBACK;"
    )
    assert replaced == "target-text-id", "Uncommitted update invisible to own transaction"
    assert sql(matching("回滚探针")) == "", "Rolled-back sparse data leaked"
    assert sql(matching()) == "target-text-id", "Rollback lost original sparse record"
    deleted = sql(
        "BEGIN; DELETE FROM probe_chunks WHERE chunk_id='target-text-id';\n"
        + matching()
        + ";ROLLBACK;"
    )
    assert deleted == "", "Uncommitted delete still searchable"
    assert sql(matching()) == "target-text-id", "Delete rollback lost original sparse record"
    checks["update_delete_rollback"] = True

    dense = (
        "SELECT c.chunk_id FROM probe_chunks c JOIN probe_documents d "
        "ON c.document_id=d.document_id AND c.document_version=d.document_version "
        "WHERE d.domain='platform_help' ORDER BY c.embedding <=> "
        "('[1,' || repeat('0,',1022) || '0]')::vector,c.chunk_id LIMIT 1"
    )
    # Hold one real REPEATABLE READ connection across a committed replacement
    # from another backend. Both native indices must retain the reader's source.
    reader = subprocess.Popen(
        prefix, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )
    try:
        reader.stdin.write("BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;\n" + dense + ";\n")
        reader.stdin.flush()
        first_dense = reader.stdout.readline().strip()
        assert first_dense == "target-text-id", "Initial dense snapshot differs"
        sql(
            "BEGIN; UPDATE probe_documents SET document_version='v2' "
            "WHERE document_id='target-doc'; DELETE FROM probe_chunks "
            "WHERE document_id='target-doc'; INSERT INTO probe_chunks VALUES "
            "('target-text-id-v2','target-doc','v2','退款 新版本 dev-user',"
            "('[1,' || repeat('0,',1022) || '0]')::vector);COMMIT;"
        )
        stdout, stderr = reader.communicate(dense + ";\n" + matching() + ";\nCOMMIT;\n")
        assert reader.returncode == 0, stderr
        assert stdout.strip().splitlines() == [first_dense, first_dense], (
            "Mixed dense/sparse snapshot"
        )
    finally:
        if reader.poll() is None:
            reader.kill()
            reader.communicate()
    assert sql(dense) == "target-text-id-v2", "Committed dense update missing"
    assert sql(matching()) == "target-text-id-v2", "Committed sparse update missing"
    assert (
        sql(
            "SELECT count(*) FROM probe_chunks c JOIN probe_documents d "
            "ON c.document_id=d.document_id AND c.document_version=d.document_version "
            "WHERE c.chunk_id='target-text-id'"
        )
        == "0"
    ), "Old source remains valid"
    checks["repeatable_read_dense_sparse_and_final_source_invalidation"] = True
    sql("DELETE FROM probe_chunks WHERE chunk_id='target-text-id-v2'")
    assert sql(matching()) == "", "Committed sparse delete missing"
    assert sql(dense) == "", "Committed dense delete missing"
    sql(
        "INSERT INTO probe_chunks VALUES ('restart-text-id','target-doc','v2',"
        "'退款 dev-user 重启持久化',('[1,' || repeat('0,',1022) || '0]')::vector)"
    )
    before = sql("SELECT pg_postmaster_start_time();" + matching() + ";" + dense)
    require("docker", "restart", container)
    for _ in range(30):
        if command("docker", "exec", container, "pg_isready", "-U", "postgres")["exit_code"] == 0:
            break
        time.sleep(1)
    after = sql("SELECT pg_postmaster_start_time();" + matching() + ";" + dense)
    assert before.splitlines()[1:] == after.splitlines()[1:] == ["restart-text-id"] * 2
    assert before.splitlines()[0] != after.splitlines()[0], "Restart not observed"
    checks["restart_persistence"] = {"before": before.splitlines(), "after": after.splitlines()}
    return checks


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--package", type=Path, help="Optional already downloaded official package")
    parser.add_argument("--load-only", action="store_true", help="Stop before semantic checks")
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
        "probe_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "started_at": datetime.now(UTC).isoformat(),
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
LABEL codex.v201111="{token}"
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
        if not args.load_only:
            evidence["semantic_checks"] = "started_not_completed"
            evidence["semantic_checks"] = semantics(require, container)
            evidence["status"] = "COMPATIBILITY_PASSED"
    except (RuntimeError, OSError, AssertionError) as error:
        evidence["status"] = "BLOCKED"
        evidence["failure"] = str(error)
    finally:
        # Delete only exact resources generated in this invocation; no broad prune.
        for resource_args in [
            ("rm", "-f", container),
            ("volume", "rm", volume),
            ("image", "rm", image),
        ]:
            record("docker", *resource_args)
        # LABEL is the first layer so failed legacy RUN containers and images
        # also carry this invocation's identity. Never prune a shared builder.
        for list_args, remove_args in [
            (("ps", "-aq"), ("rm", "-f")),
            (("image", "ls", "-aq"), ("image", "rm")),
        ]:
            result = record("docker", *list_args, "--filter", "label=codex.v201111=" + token)
            if result["exit_code"] == 0:
                for resource_id in dict.fromkeys(result["stdout"].splitlines()):
                    record("docker", *remove_args, resource_id)
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
        evidence["finished_at"] = datetime.now(UTC).isoformat()
        args.output.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({k: v for k, v in evidence.items() if k != "commands"}, ensure_ascii=False))
    return (
        0
        if (
            evidence["status"] in ("LOAD_PASSED_SEMANTICS_PENDING", "COMPATIBILITY_PASSED")
            and evidence["protected_unchanged"]
            and evidence["cleanup_complete"]
        )
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
