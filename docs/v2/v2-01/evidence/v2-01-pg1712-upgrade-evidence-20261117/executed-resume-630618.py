"""Explicit upgrade preparation stages; no source stop/disconnect/cutover in this version.

Use a retained, verified image and a fresh volume. Never call the rehearsal
restore path, install packages, enable pg_search, seed, or delete resources.
Private backup/configuration/SQL/error output stays in the operator's 0700 root.
"""

import argparse
import importlib.util
import json
import os
import secrets
import shutil
import time
import uuid
from pathlib import Path

HELPER_SHA = "72e82a48d034d75f659ddb729fea9cde8b7e404a4aa4f1d43264d62a2d7ecd1c"
SOURCE = "agent-engine-demo-db-postgres-1"
DATABASES = ("agent_demo", "agent_demo_test")
PG = "17.12-1.pgdg12+1"
VECTOR = "0.8.7-1.pgdg12+2"
VECTOR_SO_SHA = "586f3fbd75fdf71d93a6a56ac51365b48aaf015fafb19079b402deae75c01e62"
LABEL = "codex.pg1712upgrade"
ROOT_DATA = "/var/lib/postgresql/data"


def helper_at(path):
    import hashlib

    if hashlib.sha256(path.read_bytes()).hexdigest() != HELPER_SHA:
        raise RuntimeError("Backup helper byte identity differs from approved version")
    spec = importlib.util.spec_from_file_location("approved_backup_helper", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def inspect_private(commands, container, path):
    commands.run("docker", "inspect", container, output=path, private=True)
    return json.loads(path.read_text(encoding="utf-8"))[0]


def verify_backup(helper, directory):
    evidence = json.loads((directory / "backup-evidence.json").read_text(encoding="utf-8"))
    manifest = json.loads((directory / "private-manifest.json").read_text(encoding="utf-8"))
    if evidence["status"] != "BACKUP_COMPLETED_RESTORE_PENDING":
        raise RuntimeError("Successful approved backup evidence required")
    for item in manifest["files"]:
        path = directory / item["path"]
        if path.stat().st_size != item["bytes"] or helper.digest(path) != item["sha256"]:
            raise RuntimeError("Backup checksum verification failed")
    return manifest


def db_sql(commands, container, database, query):
    return commands.run(
        "docker",
        "exec",
        "-i",
        container,
        "psql",
        "-X",
        "-qAt",
        "-U",
        "agent_bootstrap",
        "-d",
        database,
        "-v",
        "ON_ERROR_STOP=1",
        input=query.encode(),
    )


def source_quiescence(helper, commands):
    """Observe current clients/state; this does NOT establish a persistent write fence."""
    result = {}
    clients = json.loads(
        db_sql(
            commands,
            SOURCE,
            "postgres",
            """
SELECT json_build_object('clients',count(*) FILTER(WHERE backend_type='client backend'
 AND pid<>pg_backend_pid() AND datname IN ('agent_demo','agent_demo_test')),
 'prepared',(SELECT count(*) FROM pg_prepared_xacts),
 'slots',(SELECT count(*) FROM pg_replication_slots)) FROM pg_stat_activity;
""",
        )
    )
    if any(clients.values()):
        raise RuntimeError("Source clients/prepared transactions/replication need review")
    for database in DATABASES:
        snapshot = helper.Snapshot(commands, SOURCE, database, "agent_bootstrap")
        try:
            inventory = helper.inventory(snapshot)
        finally:
            snapshot.close()
        # Current deployment has no persisted runs. Nonempty state requires a
        # trusted Runtime/approval/unknown review, not inference from a JSON blob.
        nonempty = {
            name: row["count"]
            for name, row in inventory["rows"].items()
            if name
            not in (
                "public.demo_orders",
                "public.schema_migrations",
                "public.checkpoint_migrations",
                "public.store_migrations",
            )
            and row["count"]
        }
        if nonempty or inventory["rows"]["public.demo_orders"]["count"] != 5:
            raise RuntimeError("Source state differs from reviewed idle five-order baseline")
        result[database] = {"tables": inventory["rows"], "persisted_active_state_empty": True}
    return {"observation_only_not_write_fence": True, "clients": clients, "databases": result}


def preflight(args, helper, commands, work):
    original = inspect_private(commands, SOURCE, work / "source-inspect.private.json")
    networks = original["NetworkSettings"]["Networks"]
    if len(networks) != 1 or not original["State"]["Running"]:
        raise RuntimeError("Expected one running source bridge endpoint")
    image = commands.run(
        "docker", "image", "inspect", "--format", "{{.Id}}|{{.Architecture}}|{{.Os}}", args.image
    )
    if not image.endswith("|amd64|linux"):
        raise RuntimeError("Verified local linux/amd64 image required")
    baseline = source_quiescence(helper, commands)
    manifest = verify_backup(helper, args.backup_dir)
    disk = shutil.disk_usage(args.workspace)
    # Explicit operator budget includes two ~83MB volumes, WAL and tests; no prune.
    if args.minimum_free_bytes is None or disk.free < args.minimum_free_bytes:
        raise RuntimeError("Operator disk peak budget missing or unavailable")
    name, endpoint = next(iter(networks.items()))
    if original["HostConfig"]["PortBindings"] != {
        "5432/tcp": [{"HostIp": "192.168.150.101", "HostPort": "5432"}]
    }:
        raise RuntimeError("Source endpoint differs from approved unchanged .env target")
    return {
        "status": "PREFLIGHT_OBSERVED_NOT_FENCED",
        "source_id": original["Id"],
        "source_identity": helper.source_identity(commands),
        "image": args.image,
        "image_id": image.split("|")[0],
        "source_network": name,
        "source_ip": endpoint["IPAddress"],
        "source_aliases": endpoint.get("Aliases"),
        "source_observation": baseline,
        "root_free_bytes": disk.free,
        "operator_peak_budget_bytes": args.minimum_free_bytes,
        "backup_dir": str(args.backup_dir),
        "backup_token": manifest["token"],
        "private_source_inspect": str(work / "source-inspect.private.json"),
        "production_extensions": ["plpgsql", "vector"],
        "pg_search_enabled": False,
        "next_step": "validation restore only; persistent source fence is a later explicit stage",
    }


def restore(args, helper, commands, work):
    prior = json.loads(args.preflight.read_text(encoding="utf-8"))
    if prior["status"] != "PREFLIGHT_OBSERVED_NOT_FENCED":
        raise RuntimeError("Reviewed preflight required")
    manifest = verify_backup(helper, args.backup_dir)
    if manifest["token"] != prior["backup_token"]:
        raise RuntimeError("Backup differs from reviewed preflight")
    current_id = commands.run("docker", "image", "inspect", "--format", "{{.Id}}", prior["image"])
    if current_id != prior["image_id"]:
        raise RuntimeError("Local image tag moved; review immutable image identity")
    if helper.source_identity(commands) != prior["source_identity"]:
        raise RuntimeError("Source changed since preflight")
    token = uuid.uuid4().hex[:12]
    container, volume, network = (
        "pg1712-validation-" + token,
        "pg1712-validation-data-" + token,
        "pg1712-validation-net-" + token,
    )
    state = {
        "status": "VALIDATION_RESTORE_IN_PROGRESS",
        "token": token,
        "container": container,
        "volume": volume,
        "network": network,
        "image_id": current_id,
        "backup_dir": str(args.backup_dir),
        "private_work": str(work),
        "resources_retained": True,
        "production_extensions": ["plpgsql", "vector"],
        "pg_search_enabled": False,
    }

    def save():
        helper.write_json(args.output, {**state, "commands": commands.events})

    def sql(database, query):
        return db_sql(commands, container, database, query)

    try:
        commands.run("docker", "network", "create", "--label", LABEL + "=" + token, network)
        commands.run("docker", "volume", "create", "--label", LABEL + "=" + token, volume)
        password = work / "bootstrap-password.private"
        password.write_text(secrets.token_urlsafe(32), encoding="utf-8")
        commands.run(
            "docker",
            "run",
            "-d",
            "--name",
            container,
            "--network",
            network,
            "--label",
            LABEL + "=" + token,
            "--memory",
            "768m",
            "--cpus",
            "1",
            "-e",
            "POSTGRES_USER=agent_bootstrap",
            "-e",
            "POSTGRES_DB=postgres",
            "-e",
            "POSTGRES_PASSWORD_FILE=/run/secrets/bootstrap-password",
            "-e",
            "POSTGRES_HOST_AUTH_METHOD=scram-sha-256",
            "--mount",
            f"type=bind,source={password},target=/run/secrets/bootstrap-password,readonly",
            "--mount",
            f"type=volume,source={volume},target={ROOT_DATA}",
            current_id,
        )
        save()
        deadline = time.monotonic() + 60
        while True:
            try:
                sql("postgres", "SELECT 1")
                break
            except RuntimeError:
                if time.monotonic() >= deadline:
                    raise RuntimeError("Validation cluster startup deadline exceeded") from None
                time.sleep(1)
        installed = commands.run(
            "docker",
            "exec",
            container,
            "dpkg-query",
            "-W",
            "postgresql-17",
            "postgresql-client-17",
            "postgresql-17-pgvector",
        )
        if any(
            line.split("\t")[-1] != (VECTOR if "pgvector" in line else PG)
            for line in installed.splitlines()
        ):
            raise RuntimeError("Retained image package versions differ from approval")
        so = commands.run(
            "docker", "exec", container, "sha256sum", "/usr/lib/postgresql/17/lib/vector.so"
        ).split()[0]
        if so != VECTOR_SO_SHA:
            raise RuntimeError("Vector binary differs from vendor-approved build")
        globals_file = args.backup_dir / "private/globals.sql"
        lines = globals_file.read_bytes().splitlines(keepends=True)
        skip = b"CREATE ROLE agent_bootstrap;"
        if sum(line.rstrip(b"\r\n") == skip for line in lines) != 1:
            raise RuntimeError("Expected one exact bootstrap role CREATE")
        derived = work / "globals.restore.private.sql"
        derived.write_bytes(b"".join(line for line in lines if line.rstrip(b"\r\n") != skip))
        commands.run(
            "docker",
            "exec",
            "-i",
            container,
            "psql",
            "-X",
            "-q",
            "-U",
            "agent_bootstrap",
            "-d",
            "postgres",
            "-v",
            "ON_ERROR_STOP=1",
            input=derived.read_bytes(),
            private=True,
        )
        for database in DATABASES:
            commands.run(
                "docker",
                "exec",
                "-i",
                container,
                "pg_restore",
                "-U",
                "agent_bootstrap",
                "--exit-on-error",
                "--create",
                "-d",
                "postgres",
                input=(args.backup_dir / f"private/{database}.dump").read_bytes(),
                timeout=600,
                private=True,
            )
            sql(database, "ANALYZE")
            snapshot = helper.Snapshot(commands, container, database, "agent_bootstrap")
            try:
                if helper.inventory(snapshot) != manifest["databases"][database]:
                    raise RuntimeError("Clean restored database inventory differs: " + database)
            finally:
                snapshot.close()
        expected_globals = json.loads(
            (args.backup_dir / "private/globals-normalized.private.json").read_text(
                encoding="utf-8"
            )
        )
        if helper.normalized_globals(commands, container) != expected_globals:
            raise RuntimeError("Restored globals differ")
        if sql("postgres", "SHOW shared_preload_libraries"):
            raise RuntimeError("Production upgrade must retain empty preload")
        original = json.loads(Path(prior["private_source_inspect"]).read_text(encoding="utf-8"))[0]
        config_map = dict(
            zip(
                manifest["configuration_paths"],
                sorted((args.backup_dir / "private/config").glob("*.conf")),
                strict=True,
            )
        )
        hba = work / "pg_hba.active.private.conf"
        shutil.copyfile(config_map["/etc/postgresql/pg_hba.conf"], hba)
        os.chown(hba, 999, 999)
        os.chmod(hba, 0o600)
        commands.run("docker", "stop", container)
        for source_path, file in config_map.items():
            if source_path.startswith(ROOT_DATA + "/"):
                commands.run("docker", "cp", str(file), container + ":" + source_path)
        # Recreate only the new validation container, retaining it as bootstrap
        # evidence and attaching its same fresh volume to the regression container.
        archived = container + "-bootstrap"
        commands.run("docker", "rename", container, archived)
        finish_validation(args, helper, commands, state, prior, manifest, original, hba)
    except (RuntimeError, OSError, ValueError) as error:
        state.update(status="VALIDATION_FAILED_RETAINED", failure=str(error))
    finally:
        save()
    return state


def finish_validation(args, helper, commands, state, prior, manifest, original, hba):
    """Start the preserved restore with source configuration and verify its contents."""
    container, token = state["container"], state["token"]
    config_map = dict(
        zip(
            manifest["configuration_paths"],
            sorted((args.backup_dir / "private/config").glob("*.conf")),
            strict=True,
        )
    )
    source_hba = config_map["/etc/postgresql/pg_hba.conf"]
    hba_stat = hba.stat()
    if hba_stat.st_uid != 999 or hba_stat.st_gid != 999 or hba_stat.st_mode & 0o777 != 0o600:
        raise RuntimeError("Preserved HBA ownership or permissions differ")
    if helper.digest(source_hba) != helper.digest(hba):
        raise RuntimeError("Preserved HBA differs from source backup")
    commands.run(
        "docker",
        "run",
        "--detach",
        "--name",
        container,
        "--network",
        state["network"],
        "--label",
        LABEL + "=" + token,
        "--memory",
        "768m",
        "--cpus",
        "1",
        "-p",
        f"192.168.150.101:{args.validation_port}:5432",
        "-e",
        "POSTGRES_USER=agent_bootstrap",
        "-e",
        "POSTGRES_DB=postgres",
        "--mount",
        f"type=volume,source={state['volume']},target={ROOT_DATA}",
        "--mount",
        f"type=bind,source={hba},target=/etc/postgresql/pg_hba.conf,readonly",
        state["image_id"],
        *original["Config"]["Cmd"][1:],
    )
    deadline = time.monotonic() + 60
    while True:
        try:
            db_sql(commands, container, "postgres", "SELECT 1")
            break
        except RuntimeError:
            if time.monotonic() >= deadline:
                raise RuntimeError("Restored original configuration did not start") from None
            time.sleep(1)

    def sql(database, query):
        return db_sql(commands, container, database, query)

    if sql("postgres", "SHOW server_version_num") != "170012":
        raise RuntimeError("Validation server version differs from 17.12")
    if sql("postgres", "SHOW shared_preload_libraries"):
        raise RuntimeError("Copied source configuration unexpectedly enabled preload")
    installed = commands.run(
        "docker",
        "exec",
        container,
        "dpkg-query",
        "-W",
        "postgresql-17",
        "postgresql-client-17",
        "postgresql-17-pgvector",
    )
    if any(
        line.split("\t")[-1] != (VECTOR if "pgvector" in line else PG)
        for line in installed.splitlines()
    ):
        raise RuntimeError("Retained image package versions differ from approval")
    so = commands.run(
        "docker", "exec", container, "sha256sum", "/usr/lib/postgresql/17/lib/vector.so"
    ).split()[0]
    if so != VECTOR_SO_SHA:
        raise RuntimeError("Vector binary differs from vendor-approved build")
    for database in DATABASES:
        snapshot = helper.Snapshot(commands, container, database, "agent_bootstrap")
        try:
            if helper.inventory(snapshot) != manifest["databases"][database]:
                raise RuntimeError("Restored database inventory differs: " + database)
        finally:
            snapshot.close()
    expected_globals = json.loads(
        (args.backup_dir / "private/globals-normalized.private.json").read_text(encoding="utf-8")
    )
    if helper.normalized_globals(commands, container) != expected_globals:
        raise RuntimeError("Restored globals differ")
    if helper.source_identity(commands) != prior["source_identity"]:
        raise RuntimeError("Source changed since preflight")
    marker = "pg1712-upgrade-validation:" + token
    sql("postgres", "COMMENT ON DATABASE postgres IS '" + marker + "'")
    if (
        sql(
            "postgres",
            "SELECT shobj_description(oid,'pg_database') FROM pg_database WHERE datname='postgres'",
        )
        != marker
    ):
        raise RuntimeError("Validation marker mismatch")
    ip = commands.run(
        "docker",
        "inspect",
        "--format",
        "{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}",
        container,
    )
    state.update(
        status="VALIDATION_READY_NO_CUTOVER",
        ip=ip,
        host="192.168.150.101",
        host_port=args.validation_port,
        token_marker=marker,
        package_versions=installed,
        vector_so_sha256=so,
        source_hba_sha256=helper.digest(source_hba),
        validation_hba_sha256=helper.digest(hba),
        original_hba_exact=True,
        analyzed=True,
        clean_inventory_equal=True,
        globals_match=True,
        bootstrap_container_retained=container + "-bootstrap",
    )


def resume_validation(args, helper, commands, work):
    """Resume only the retained stopped bootstrap and its already restored volume."""
    # This receipt predates the exception; only its independently reviewed attempt is resumable.
    if (
        helper.digest(args.receipt)
        != "01fee08ea6f0dc93460c76fedd2cb6be8ba78851da1382a4ed8144a09b97ce90"
    ):
        raise RuntimeError("Receipt differs from reviewed interrupted attempt")
    state = json.loads(args.receipt.read_text(encoding="utf-8"))
    prior = json.loads(args.preflight.read_text(encoding="utf-8"))
    if (
        state["status"] != "VALIDATION_RESTORE_IN_PROGRESS"
        or prior["status"] != "PREFLIGHT_OBSERVED_NOT_FENCED"
    ):
        raise RuntimeError("Expected original in-progress receipt and reviewed preflight")
    token = state["token"]
    if (
        len(token) != 12
        or any(c not in "0123456789abcdef" for c in token)
        or state["container"] != "pg1712-validation-" + token
        or state["volume"] != "pg1712-validation-data-" + token
        or state["network"] != "pg1712-validation-net-" + token
    ):
        raise RuntimeError("Receipt resource names or token invalid")
    if str(args.backup_dir) != state["backup_dir"]:
        raise RuntimeError("Backup directory differs from receipt")
    manifest = verify_backup(helper, args.backup_dir)
    if manifest["token"] != prior["backup_token"]:
        raise RuntimeError("Backup differs from reviewed preflight")
    current_id = commands.run("docker", "image", "inspect", "--format", "{{.Id}}", prior["image"])
    if current_id != prior["image_id"] or current_id != state["image_id"]:
        raise RuntimeError("Image identity differs from preflight or receipt")
    original = json.loads(Path(prior["private_source_inspect"]).read_text(encoding="utf-8"))[0]
    if (
        original["Id"] != prior["source_id"]
        or helper.source_identity(commands) != prior["source_identity"]
    ):
        raise RuntimeError("Source identity differs from preflight")
    bootstrap = inspect_private(
        commands, state["container"] + "-bootstrap", work / "bootstrap-inspect.private.json"
    )
    if (
        bootstrap["State"]["Running"]
        or bootstrap["Image"] != current_id
        or bootstrap["Config"]["Labels"].get(LABEL) != token
        or state["network"] not in bootstrap["NetworkSettings"]["Networks"]
        or not any(
            m["Type"] == "volume" and m["Name"] == state["volume"] and m["Destination"] == ROOT_DATA
            for m in bootstrap["Mounts"]
        )
    ):
        raise RuntimeError("Stopped bootstrap identity or volume differs")
    for kind in ("volume", "network"):
        obj = json.loads(commands.run("docker", kind, "inspect", state[kind]))[0]
        if obj["Labels"].get(LABEL) != token or obj["Name"] != state[kind]:
            raise RuntimeError("Retained " + kind + " identity differs")
    hba = Path(state["private_work"]) / "pg_hba.active.private.conf"
    state = {k: v for k, v in state.items() if k != "commands"}
    state.update(
        status="VALIDATION_RESUME_IN_PROGRESS",
        resumed_from=str(args.receipt),
        restored_private_work=state["private_work"],
    )
    try:
        finish_validation(args, helper, commands, state, prior, manifest, original, hba)
    except (RuntimeError, OSError, ValueError) as error:
        state.update(status="VALIDATION_FAILED_RETAINED", failure=str(error))
    return state


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("preflight", "restore", "resume-validation"))
    parser.add_argument("--helper", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--backup-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--image")
    parser.add_argument("--minimum-free-bytes", type=int)
    parser.add_argument("--preflight", type=Path)
    parser.add_argument("--receipt", type=Path)
    parser.add_argument("--validation-port", type=int, default=56322)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Fresh evidence output required; retain prior attempts")
    if args.stage == "preflight" and (not args.image or args.minimum_free_bytes is None):
        parser.error("Explicit retained image and operator disk budget required")
    if args.stage in ("restore", "resume-validation") and args.preflight is None:
        parser.error("Reviewed preflight evidence required")
    if args.stage == "resume-validation" and (
        args.receipt is None or args.validation_port != 56322
    ):
        parser.error("resume-validation requires original --receipt and port 56322")
    if args.validation_port == 5432 or not 1024 <= args.validation_port <= 65535:
        parser.error("Independent validation port required; production 5432 is forbidden")
    os.umask(0o077)
    helper = helper_at(args.helper)
    work = args.workspace / (args.stage + "-" + uuid.uuid4().hex[:12])
    work.mkdir(mode=0o700)
    commands = helper.Commands(work, 90)
    try:
        result = (
            preflight(args, helper, commands, work)
            if args.stage == "preflight"
            else resume_validation(args, helper, commands, work)
            if args.stage == "resume-validation"
            else restore(args, helper, commands, work)
        )
    except (RuntimeError, OSError, ValueError) as error:
        result = {"status": "FAILED_RETAINED", "failure": str(error)}
    result["upgrade_script_sha256"] = helper.digest(Path(__file__))
    result["private_work"] = str(work)
    result["commands"] = commands.events
    helper.write_json(args.output, result)
    print(json.dumps({key: result.get(key) for key in ("status", "failure", "container", "ip")}))
    return (
        0
        if result["status"] in ("PREFLIGHT_OBSERVED_NOT_FENCED", "VALIDATION_READY_NO_CUTOVER")
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
