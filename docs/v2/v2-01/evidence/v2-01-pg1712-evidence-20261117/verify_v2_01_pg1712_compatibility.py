"""One isolated PG17.12/pgvector/pg_search experiment; never upgrades the original DB.

Run on the authorized Docker VM. Pin --base-image to the approved amd64 digest
and --pg-package/--vector-package to versions found by the read-only preflight.
Build output is streamed to the evidence directory, not buffered until completion.
"""

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import tempfile
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

PROTECTED = "agent-engine-demo-db-postgres-1"
PACKAGE_SHA = "16a14d382f088bc23e7c8624e4860fd8bf01a939c67c7695348de0615e323ddb"
SYMBOL = "pg_mblen_cstr"
LABEL = "codex.v201pg1712"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-image", required=True)
    parser.add_argument("--pg-package", required=True)
    parser.add_argument("--vector-package", required=True)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--command-timeout", type=int, default=90)
    parser.add_argument("--build-timeout", type=int, default=1200)
    parser.add_argument("--startup-timeout", type=int, default=60)
    args = parser.parse_args()
    if not re.fullmatch(r"postgres:17\.12-bookworm@sha256:[0-9a-f]{64}", args.base_image):
        parser.error("Only a fixed postgres:17.12-bookworm digest is allowed")
    if not re.fullmatch(r"17\.12-[0-9]+\.pgdg12\+[0-9]+", args.pg_package):
        parser.error("PG server/client package must be an exact 17.12 Bookworm version")
    if not re.fullmatch(r"0\.8\.7-[0-9]+\.pgdg12\+[0-9]+", args.vector_package):
        parser.error("pgvector must remain 0.8.7 with an exact Bookworm package version")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    token = uuid.uuid4().hex[:12]
    work = Path(tempfile.mkdtemp(prefix="codex-v201pg1712-"))
    image, container, volume = (
        "codex-v201pg1712:" + token,
        "codex-v201pg1712-" + token,
        "codex-v201pg1712-data-" + token,
    )
    build_log = args.output.parent / ("build-" + token + ".log")
    evidence = {
        "token": token,
        "status": "BLOCKED",
        "commands": [],
        "probe_sha256": sha(Path(__file__)),
        "base_image": args.base_image,
        "pg_package": args.pg_package,
        "vector_package": args.vector_package,
        "started_at": datetime.now(UTC).isoformat(),
        "build_log": str(build_log),
        "semantic_checks": "not_executed",
    }

    def run(*command, input=None, private=False, timeout=None, log=None):
        """Private mode hashes original rows without logging their values."""
        item = {"command": list(command), "started_at": datetime.now(UTC).isoformat()}
        try:
            if log:
                with log.open("w", encoding="utf-8") as stream:
                    result = subprocess.run(
                        command,
                        input=input,
                        text=True,
                        stdout=stream,
                        stderr=subprocess.STDOUT,
                        check=False,
                        timeout=timeout or args.command_timeout,
                    )
                item.update(exit_code=result.returncode, log=str(log), log_sha256=sha(log))
                output = ""
            else:
                result = subprocess.run(
                    command,
                    input=input,
                    text=True,
                    capture_output=True,
                    check=False,
                    timeout=timeout or args.command_timeout,
                )
                output = result.stdout.strip()
                if not private:
                    item.update(stdout=output, stderr=result.stderr.strip())
                item["exit_code"] = result.returncode
        except subprocess.TimeoutExpired:
            item.update(exit_code=124, timeout_seconds=timeout or args.command_timeout)
            output = ""
        if not private:
            evidence["commands"].append(item)
        if item["exit_code"]:
            raise RuntimeError("Command failed/expired: " + " ".join(command[:3]))
        return output

    def save():
        args.output.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n")

    def original():
        state = run(
            "docker",
            "inspect",
            "--format",
            "{{.Id}}|{{.State.StartedAt}}|{{.Config.Image}}|{{json .Mounts}}",
            PROTECTED,
        )
        packages = run(
            "docker",
            "exec",
            PROTECTED,
            "dpkg-query",
            "-W",
            "postgresql-17",
            "postgresql-client-17",
            "postgresql-17-pgvector",
        )
        executable = run(
            "docker",
            "exec",
            "-u",
            "postgres",
            PROTECTED,
            "sh",
            "-c",
            "p=$(head -n 1 /var/lib/postgresql/data/postmaster.pid); "
            "readlink -f /proc/$p/exe; /proc/$p/exe --version; sha256sum /proc/$p/exe",
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
            version = run(
                *prefix,
                "SELECT current_setting('server_version_num'),"
                "pg_postmaster_start_time(),"
                "(SELECT extversion FROM pg_extension WHERE extname='vector')",
            )
            tables = run(
                *prefix,
                "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename",
            ).splitlines()
            rows = {}
            for table in tables:
                quoted = '"' + table.replace('"', '""') + '"'
                raw = run(
                    *prefix,
                    "SELECT row_to_json(t)::text FROM public."
                    + quoted
                    + " t ORDER BY row_to_json(t)::text",
                    private=True,
                )
                rows[table] = hashlib.sha256(raw.encode()).hexdigest()
            columns = run(
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
                "version": version,
                "rows_sha256": rows,
                "columns_sha256": hashlib.sha256(columns.encode()).hexdigest(),
            }
        return {
            "container": state,
            "packages": packages,
            "running_executable": executable,
            "databases": databases,
        }

    def symbols(path):
        # readelf is an inspection tool on the VM, not installed in the original container.
        lines = run("readelf", "--dyn-syms", "--wide", str(path), private=True).splitlines()
        return [line.strip() for line in lines if line.split() and line.split()[-1] == SYMBOL]

    def tool_container(name, *options):
        return run(
            "docker",
            "create",
            "--name",
            name,
            "--network",
            "none",
            "--label",
            LABEL + "=" + token,
            *options,
        )

    def wait_ready():
        deadline = time.monotonic() + args.startup_timeout
        while time.monotonic() < deadline:
            try:
                run("docker", "exec", container, "pg_isready", "-U", "postgres")
                return
            except RuntimeError:
                time.sleep(1)
        raise RuntimeError("Isolated PG17.12 failed startup/readiness")

    try:
        run("df", "-h", "/")
        run("free", "-m")
        run("readelf", "--version")
        evidence["protected_before"] = original()
        evidence["phase"] = "symbol_inspection"
        save()
        original_exe = evidence["protected_before"]["running_executable"].splitlines()
        if original_exe[0] != "/usr/lib/postgresql/17/bin/postgres":
            raise RuntimeError("Unexpected original postmaster executable path")
        copy = work / "postgres-17.6"
        run("docker", "cp", PROTECTED + ":" + original_exe[0], str(copy))
        if sha(copy) != original_exe[2].split()[0]:
            raise RuntimeError("Copied PG17.6 differs from actual running executable")
        original_symbols = symbols(copy)
        if original_symbols:
            raise RuntimeError("PG17.6 unexpectedly exports target symbol; investigate baseline")
        target = work / "pg_search.deb"
        shutil.copyfile(args.package, target)
        if sha(target) != PACKAGE_SHA:
            raise RuntimeError("Official pg_search package SHA256 mismatch")
        run("dpkg-deb", "-f", str(target), "Package", "Version", "Architecture", "Depends")
        unpacked = work / "package"
        run("dpkg-deb", "-x", str(target), str(unpacked))
        library = unpacked / "usr/lib/postgresql/17/lib/pg_search.so"
        required = symbols(library)
        if not any(" UND " in " " + line + " " for line in required):
            raise RuntimeError("pg_search.so target undefined symbol not found")
        evidence["symbols"] = {
            "pg176_exe_sha256": sha(copy),
            "pg176_exports": original_symbols,
            "pg_search_so_sha256": sha(library),
            "pg_search_undefined": required,
        }
        shutil.rmtree(unpacked)
        copy.unlink()
        dockerfile = f"""FROM {args.base_image}
LABEL {LABEL}="{token}"
COPY pg_search.deb /tmp/pg_search.deb
RUN apt-get update && apt-get install -y --no-remove --no-install-recommends \\
    postgresql-17={args.pg_package} postgresql-client-17={args.pg_package} \\
    postgresql-17-pgvector={args.vector_package} /tmp/pg_search.deb \\
    && test \"$(dpkg-query -W -f='${{Version}}' postgresql-17)\" = '{args.pg_package}' \\
    && test \"$(dpkg-query -W -f='${{Version}}' postgresql-17-pgvector)\" \\
        = '{args.vector_package}' \\
    && rm -rf /var/lib/apt/lists/* /tmp/pg_search.deb
"""
        (work / "Dockerfile").write_text(dockerfile)
        evidence["phase"] = "build"
        save()
        run(
            "env",
            "DOCKER_BUILDKIT=0",
            "docker",
            "build",
            "--memory",
            "768m",
            "--cpu-period",
            "100000",
            "--cpu-quota",
            "100000",
            "-t",
            image,
            str(work),
            timeout=args.build_timeout,
            log=build_log,
        )
        architecture = run(
            "docker", "image", "inspect", "--format", "{{.Architecture}}|{{.Os}}|{{.Id}}", image
        )
        if not architecture.startswith("amd64|linux|"):
            raise RuntimeError("Candidate image must be Linux amd64")
        evidence["candidate_image"] = architecture
        tool = "codex-v201pg1712-copy-" + token
        tool_container(tool, image)
        pg1712 = work / "postgres-17.12"
        run("docker", "cp", tool + ":/usr/lib/postgresql/17/bin/postgres", str(pg1712))
        exported = symbols(pg1712)
        if not any(" UND " not in " " + line + " " for line in exported):
            raise RuntimeError("Candidate PG17.12 does not export pg_mblen_cstr")
        evidence["symbols"].update(pg1712_exe_sha256=sha(pg1712), pg1712_exports=exported)
        run("docker", "volume", "create", "--label", LABEL + "=" + token, volume)
        run(
            "docker",
            "run",
            "-d",
            "--name",
            container,
            "--network",
            "none",
            "--label",
            LABEL + "=" + token,
            "--memory",
            "768m",
            "--cpus",
            "1",
            "--pids-limit",
            "128",
            "-e",
            "POSTGRES_HOST_AUTH_METHOD=trust",
            "-e",
            "OPENBLAS_NUM_THREADS=1",
            "-e",
            "OMP_NUM_THREADS=1",
            "--mount",
            f"type=volume,source={volume},target=/var/lib/postgresql/data",
            image,
            "-c",
            "shared_preload_libraries=pg_search",
        )
        evidence["phase"] = "load"
        save()
        wait_ready()
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
            return run(*prefix, input=text)

        run(
            "docker",
            "exec",
            container,
            "dpkg-query",
            "-W",
            "postgresql-17",
            "postgresql-client-17",
            "postgresql-17-pgvector",
            "postgresql-17-pg-search",
            "libopenblas0",
        )
        candidate_exe = run(
            "docker",
            "exec",
            "-u",
            "postgres",
            container,
            "sh",
            "-c",
            "p=$(head -n 1 /var/lib/postgresql/data/postmaster.pid); "
            "readlink -f /proc/$p/exe; /proc/$p/exe --version; "
            "sha256sum /proc/$p/exe",
        )
        if candidate_exe.splitlines()[2].split()[0] != sha(pg1712):
            raise RuntimeError("Candidate running executable differs from inspected PG17.12")
        evidence["candidate_running_executable"] = candidate_exe
        version = sql(
            "CREATE EXTENSION vector; CREATE EXTENSION pg_search; "
            "SELECT current_setting('server_version_num'); "
            "SELECT extname,extversion FROM pg_extension ORDER BY extname;"
        )
        if not version.startswith("170012\n") or "vector|0.8.7" not in version:
            raise RuntimeError("Candidate runtime versions do not match fixed combination")
        evidence["loaded_versions"] = version
        evidence["phase"] = "minimal_bm25"
        save()
        sql(
            "CREATE TABLE compat_chunks(chunk_id text PRIMARY KEY,search_text text); "
            "INSERT INTO compat_chunks VALUES ('中文-chunk-id','申请模拟退款，需要等待审批'),"
            "('other-chunk','订单查询帮助'); "
            "CREATE INDEX compat_bm25 ON compat_chunks USING paradedb "
            "(chunk_id,(search_text::pdb.jieba('search_mode=true')));"
        )

        def search(term):
            return (
                "SELECT coalesce(json_agg(chunk_id ORDER BY chunk_id),'[]') "
                "FROM compat_chunks WHERE search_text ||| '" + term + "';"
            )

        chinese = json.loads(sql(search("退款")))
        if chinese != ["中文-chunk-id"]:
            raise RuntimeError("Minimal Chinese BM25 failed")
        evidence["bm25_plan"] = json.loads(
            sql(
                "EXPLAIN (FORMAT JSON,COSTS OFF) SELECT chunk_id FROM compat_chunks "
                "WHERE search_text ||| '退款'"
            )
        )
        changed = sql(
            "BEGIN; UPDATE compat_chunks SET search_text='物流帮助' "
            "WHERE chunk_id='中文-chunk-id';" + search("物流") + "ROLLBACK;"
        )
        if json.loads(changed) != chinese or json.loads(sql(search("退款"))) != chinese:
            raise RuntimeError("Own-transaction sparse update or rollback failed")
        if json.loads(sql(search("物流"))) != []:
            raise RuntimeError("Rolled-back term remains searchable")
        sql(
            "BEGIN; UPDATE compat_chunks SET search_text='物流帮助 重启恢复验证' "
            "WHERE chunk_id='中文-chunk-id';COMMIT;"
        )
        if json.loads(sql(search("退款"))) != [] or json.loads(sql(search("物流"))) != chinese:
            raise RuntimeError("Committed BM25 update inconsistent")
        before = sql("SELECT pg_postmaster_start_time();" + search("物流"))
        run("docker", "restart", container)
        wait_ready()
        after = sql("SELECT pg_postmaster_start_time();" + search("物流"))
        if (
            before.splitlines()[0] == after.splitlines()[0]
            or before.splitlines()[1:] != after.splitlines()[1:]
        ):
            raise RuntimeError("Restart or sparse persistence not verified")
        evidence["semantic_checks"] = {
            "chinese_text_id": chinese,
            "transaction_update": True,
            "rollback": True,
            "committed_update": True,
            "restart_before": before,
            "restart_after": after,
        }
        evidence["status"] = "ISOLATED_COMBINATION_PASSED"
    except (RuntimeError, OSError, ValueError) as error:
        evidence["failure"] = str(error)
    finally:
        try:
            # Logs contain only this synthetic, network-isolated server's output.
            run("docker", "logs", container)
        except RuntimeError:
            pass
        cleanup_errors = []
        for list_args, remove_args in [
            (("ps", "-aq"), ("rm", "-f")),
            (("volume", "ls", "-q"), ("volume", "rm")),
            (("image", "ls", "-aq"), ("image", "rm")),
        ]:
            try:
                ids = run("docker", *list_args, "--filter", "label=" + LABEL + "=" + token)
                for resource in dict.fromkeys(ids.splitlines()):
                    run("docker", *remove_args, resource)
            except RuntimeError as error:
                cleanup_errors.append(str(error))
        evidence["cleanup_errors"] = cleanup_errors
        leftovers = []
        for kind in [("ps", "-aq"), ("volume", "ls", "-q"), ("image", "ls", "-aq")]:
            try:
                leftovers.append(run("docker", *kind, "--filter", "label=" + LABEL + "=" + token))
            except RuntimeError:
                leftovers.append("query_failed")
        evidence["cleanup_complete"] = not any(leftovers)
        try:
            evidence["protected_after"] = original()
            evidence["protected_unchanged"] = (
                evidence.get("protected_before") == evidence["protected_after"]
            )
        except RuntimeError as error:
            evidence["protection_check_error"] = str(error)
            evidence["protected_unchanged"] = False
        shutil.rmtree(work)
        evidence["workspace_removed"] = not work.exists()
        evidence["finished_at"] = datetime.now(UTC).isoformat()
        if build_log.exists():
            evidence["build_log_sha256"] = sha(build_log)
        save()
    print(
        json.dumps(
            {
                key: evidence.get(key)
                for key in ("status", "failure", "protected_unchanged", "cleanup_complete")
            },
            ensure_ascii=False,
        )
    )
    return (
        0
        if (
            evidence["status"] == "ISOLATED_COMBINATION_PASSED"
            and evidence["protected_unchanged"]
            and evidence["cleanup_complete"]
        )
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
