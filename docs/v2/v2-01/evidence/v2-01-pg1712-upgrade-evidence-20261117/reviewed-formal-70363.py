"""Explicit, separately reviewed stages for the PG17.12 upgrade.

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
import socket
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
FORMAL_EXECUTION_ENABLED = False  # Independent QA must complete before enabling remote operations.


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
 AND pid<>pg_backend_pid()),
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
    if (
        args.minimum_free_bytes is None
        or args.minimum_free_bytes <= 0
        or disk.free < args.minimum_free_bytes
    ):
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
    final = args.stage == "final-restore"
    prior = json.loads(args.preflight.read_text(encoding="utf-8"))
    if prior["status"] != "PREFLIGHT_OBSERVED_NOT_FENCED":
        raise RuntimeError("Reviewed preflight required")
    manifest = verify_backup(helper, args.backup_dir)
    if final:
        verify_final_backup_receipt(args, helper, manifest, prior)
        verify_fenced(helper, commands, work, prior)
        if (
            args.minimum_free_bytes is None
            or args.minimum_free_bytes <= 0
            or shutil.disk_usage(args.workspace).free < args.minimum_free_bytes
        ):
            raise RuntimeError("Final restore remaining disk budget unavailable")
    elif manifest["token"] != prior["backup_token"]:
        raise RuntimeError("Backup differs from reviewed preflight")
    current_id = commands.run("docker", "image", "inspect", "--format", "{{.Id}}", prior["image"])
    if current_id != prior["image_id"]:
        raise RuntimeError("Local image tag moved; review immutable image identity")
    if helper.source_identity(commands) != prior["source_identity"]:
        raise RuntimeError("Source changed since preflight")
    token = uuid.uuid4().hex[:12]
    prefix = "pg1712-final-" if final else "pg1712-validation-"
    container, volume, network = (prefix + token, prefix + "data-" + token, prefix + "net-" + token)
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

    save()
    try:
        commands.run(
            "docker",
            "network",
            "create",
            *(["--internal"] if final else []),
            "--label",
            LABEL + "=" + token,
            network,
        )
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
        finish_validation(
            args, helper, commands, state, prior, manifest, original, hba, final=final
        )
        if final:
            verify_fenced(helper, commands, work, prior)
    except (RuntimeError, OSError, ValueError) as error:
        state.update(status="VALIDATION_FAILED_RETAINED", failure=str(error))
    finally:
        save()
    return state


def finish_validation(args, helper, commands, state, prior, manifest, original, hba, final=False):
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
        *([] if final else ["-p", f"192.168.150.101:{args.validation_port}:5432"]),
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
    marker = None if final else "pg1712-upgrade-validation:" + token
    if marker:
        sql("postgres", "COMMENT ON DATABASE postgres IS '" + marker + "'")
    if marker and (
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
        status="FINAL_RESTORE_VERIFIED" if final else "VALIDATION_READY_NO_CUTOVER",
        ip=ip,
        host=None if final else "192.168.150.101",
        host_port=None if final else args.validation_port,
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


SOURCE_NETWORK = "agent-engine-demo-db_default"
SOURCE_IP = "172.19.0.2"
SOURCE_ALIASES = {"postgres", SOURCE}


def verify_validation_gate(args, helper):
    gate = json.loads(args.validation_gate.read_text(encoding="utf-8"))
    validation = json.loads(args.validation_receipt.read_text(encoding="utf-8"))
    outcomes = gate["pytest_outcomes"]
    if (
        gate["status"] != "VALIDATION_FULL_GATE_PASSED"
        or gate["validation_token"] != "6b522e463c2b"
        or validation["status"] != "VALIDATION_READY_NO_CUTOVER"
        or validation["token"] != gate["validation_token"]
        or helper.digest(args.validation_receipt) != gate["validation_receipt_sha256"]
        or gate["pytest_exit"] != 0
        or outcomes["passed"] <= 0
        or outcomes["failed"] != 0
        or outcomes["skipped"] != 0
        or gate["protected_unchanged"] is not True
        or len(gate["full_report_sha256"]) != 64
        or len(gate["qwen_evidence_sha256"]) != 64
    ):
        raise RuntimeError("Matching trusted full validation gate required")


def verify_final_backup_receipt(args, helper, manifest, prior):
    windows = json.loads(args.windows_receipt.read_text(encoding="utf-8"))
    backup = json.loads((args.backup_dir / "backup-evidence.json").read_text(encoding="utf-8"))
    if (
        windows["status"] != "WINDOWS_FINAL_BACKUP_VERIFIED"
        or windows["backup_directory_remote"] != str(args.backup_dir)
        or windows["backup_token"] != manifest["token"]
        or windows["manifest_sha256"] != helper.digest(args.backup_dir / "private-manifest.json")
        or windows["files_verified"] != len(manifest["files"])
        or windows["payload_bytes"] != sum(item["bytes"] for item in manifest["files"])
        or windows["all_files_match"] is not True
        or windows["private_acl_restricted"] is not True
        or windows["fsync_completed"] is not True
        or backup["source_before"] != prior["source_identity"]
        or backup["source_after"] != prior["source_identity"]
    ):
        raise RuntimeError("Verified offsite final backup receipt required")
    freeze_state = json.loads(args.receipt.read_text(encoding="utf-8"))
    backup_stage = json.loads(args.backup_receipt.read_text(encoding="utf-8"))
    if (
        backup_stage["status"] != "FINAL_BACKUP_REQUIRES_OFFSITE_VERIFICATION"
        or backup_stage["freeze_receipt"] != str(args.receipt)
        or backup_stage["backup_directory"] != str(args.backup_dir)
        or backup_stage["backup_token"] != manifest["token"]
        or backup_stage["source_id"] != prior["source_id"]
    ):
        raise RuntimeError("Matching fenced final backup stage required")
    if freeze_state["status"] != "SOURCE_FENCED" or freeze_state["source_id"] != prior["source_id"]:
        raise RuntimeError("Matching source freeze receipt required")


def read_preflight(args):
    prior = json.loads(args.preflight.read_text(encoding="utf-8"))
    if (
        prior["status"] != "PREFLIGHT_OBSERVED_NOT_FENCED"
        or prior["source_network"] != SOURCE_NETWORK
        or prior["source_ip"] != SOURCE_IP
        or set(prior["source_aliases"]) != SOURCE_ALIASES
    ):
        raise RuntimeError("Preflight does not match reviewed source endpoint")
    return prior


def verify_fenced(helper, commands, work, prior):
    """Check the original container is running but has no Docker network endpoint."""
    source = inspect_private(commands, SOURCE, work / (uuid.uuid4().hex + ".private.json"))
    if (
        source["Id"] != prior["source_id"]
        or not source["State"]["Running"]
        or source["NetworkSettings"]["Networks"]
        or helper.source_identity(commands) != prior["source_identity"]
    ):
        raise RuntimeError("Source fence or identity differs from reviewed original")
    # Docker's proxy can retain the listening socket after network disconnect.
    # Only a closed connection proves this probe did not reach PostgreSQL.
    import struct

    packet = b"user\0agent_bootstrap\0database\0postgres\0\0"
    packet = struct.pack("!II", len(packet) + 8, 196608) + packet
    try:
        with socket.create_connection(("192.168.150.101", 5432), timeout=3) as sock:
            sock.settimeout(3)
            sock.sendall(packet)
            if sock.recv(1):
                raise RuntimeError("Original PostgreSQL protocol remains externally reachable")
    except (ConnectionRefusedError, ConnectionResetError, BrokenPipeError):
        pass
    return source_quiescence(helper, commands)


def write_freeze_journal(path, state, *, create=False):
    """Persist the recovery record before changing the source network."""
    temporary = path if create else path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        if path.name != "writes-opened.journal":
            owner = path.parent.stat()
            os.fchown(stream.fileno(), owner.st_uid, owner.st_gid)
        json.dump(state, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    if not create:
        os.replace(temporary, path)
    directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


SOURCE_HBA = Path("/home/white7/agent-engine-demo-db/pg_hba.conf")


def persist_hba_snapshot(directory, name, data):
    """Keep a private immutable preimage or target before publishing its write intent."""
    path = directory / ("source-hba-" + name + "-" + uuid.uuid4().hex + ".private")
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    directory_fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)
    return path


def hba_write_state_valid(current, before, after):
    """A sequential overwrite can leave a new prefix followed by the old suffix."""
    return current == after or any(
        current == after[:written] + before[written:] for written in range(len(after) + 1)
    )


def inplace_source_hba(state, helper, desired):
    """Persist each preimage and write intent before changing the existing Docker bind inode."""
    path = Path(state["source_hba_path"])
    backup = Path(state["source_hba_backup"])
    original = backup.read_bytes()
    if helper.digest(backup) != state["source_hba_sha256"]:
        raise RuntimeError("Private original source HBA backup differs")
    if desired not in (original, MAINTENANCE_HBA):
        raise RuntimeError("Unapproved source HBA target")
    intent_path = backup.parent / "source-hba-write-intent.private.json"
    fd = os.open(path, os.O_RDWR | os.O_NOFOLLOW | getattr(os, "O_BINARY", 0))
    try:
        info = os.fstat(fd)
        if (
            info.st_dev != state["source_hba_device"]
            or info.st_ino != state["source_hba_inode"]
            or info.st_uid != state["source_hba_uid"]
            or info.st_gid != state["source_hba_gid"]
            or info.st_mode & 0o7777 != state["source_hba_mode"]
        ):
            raise RuntimeError("Source HBA inode or metadata changed; manual review required")
        pieces = []
        while chunk := os.read(fd, 65536):
            pieces.append(chunk)
        existing = b"".join(pieces)
        if intent_path.exists():
            intent = json.loads(intent_path.read_text(encoding="utf-8"))
            before_path, after_path = Path(intent["from_path"]), Path(intent["to_path"])
            if (
                intent["device"] != info.st_dev
                or intent["inode"] != info.st_ino
                or before_path.parent != backup.parent
                or after_path.parent != backup.parent
                or helper.digest(before_path) != intent["from_sha256"]
                or helper.digest(after_path) != intent["to_sha256"]
            ):
                raise RuntimeError("Source HBA write intent or private snapshots differ")
            before, after = before_path.read_bytes(), after_path.read_bytes()
            if (
                intent["phase"] == "pending"
                and not hba_write_state_valid(existing, before, after)
                or intent["phase"] == "completed"
                and existing != after
                or intent["phase"] not in ("pending", "completed")
            ):
                raise RuntimeError(
                    "Source HBA does not match recorded write intent; refusing overwrite"
                )
        elif existing not in (original, MAINTENANCE_HBA):
            raise RuntimeError("Source HBA changed unexpectedly; refusing to overwrite")
        if existing != desired:
            # Each recovery has its own preimage, so it too can be interrupted safely.
            before_path = persist_hba_snapshot(backup.parent, "from", existing)
            after_path = persist_hba_snapshot(backup.parent, "to", desired)
            intent = {
                "phase": "pending",
                "device": info.st_dev,
                "inode": info.st_ino,
                "from_path": str(before_path),
                "from_sha256": helper.digest(before_path),
                "to_path": str(after_path),
                "to_sha256": helper.digest(after_path),
            }
            write_freeze_journal(intent_path, intent, create=not intent_path.exists())
            path_info = path.stat(follow_symlinks=False)
            if (path_info.st_dev, path_info.st_ino) != (info.st_dev, info.st_ino):
                raise RuntimeError("Source HBA path changed before in-place update")
            os.lseek(fd, 0, os.SEEK_SET)
            offset = 0
            while offset < len(desired):
                written = os.write(fd, desired[offset:])
                if written <= 0:
                    raise OSError("Source HBA write made no progress")
                offset += written
            os.ftruncate(fd, len(desired))
            os.fsync(fd)
            intent["phase"] = "completed"
            write_freeze_journal(intent_path, intent)
        after_info = os.fstat(fd)
        path_info = path.stat(follow_symlinks=False)
        if (
            after_info.st_dev,
            after_info.st_ino,
            after_info.st_uid,
            after_info.st_gid,
            after_info.st_mode & 0o7777,
        ) != (info.st_dev, info.st_ino, info.st_uid, info.st_gid, info.st_mode & 0o7777) or (
            path_info.st_dev,
            path_info.st_ino,
        ) != (info.st_dev, info.st_ino):
            raise RuntimeError("Source HBA path or metadata changed during in-place update")
    finally:
        os.close(fd)
    return original


def reload_source_hba(commands, helper, expected_sha):
    """Wait for a successful PostgreSQL reload and check the bound file and parse errors."""
    actual = commands.run(
        "docker", "exec", SOURCE, "sha256sum", "/etc/postgresql/pg_hba.conf"
    ).split()[0]
    if actual != expected_sha:
        raise RuntimeError("Source container does not see the expected HBA bytes")
    before = db_sql(commands, SOURCE, "postgres", "SELECT pg_conf_load_time()")
    if db_sql(commands, SOURCE, "postgres", "SELECT pg_reload_conf()") != "t":
        raise RuntimeError("Source PostgreSQL rejected reload")
    deadline = time.monotonic() + 30
    while db_sql(commands, SOURCE, "postgres", "SELECT pg_conf_load_time()") == before:
        if time.monotonic() >= deadline:
            raise RuntimeError("Source PostgreSQL reload deadline exceeded")
        time.sleep(0.5)
    if (
        db_sql(
            commands,
            SOURCE,
            "postgres",
            "SELECT count(*) FROM pg_hba_file_rules WHERE error IS NOT NULL",
        )
        != "0"
        or db_sql(
            commands,
            SOURCE,
            "postgres",
            "SELECT count(*) FROM pg_file_settings WHERE error IS NOT NULL",
        )
        != "0"
    ):
        raise RuntimeError("Source PostgreSQL configuration reports reload errors")


def restore_source_hba(state, helper, commands):
    """Restore the exact original HBA in place and reload before any reconnection."""
    if commands.run("docker", "inspect", "--format", "{{.Id}}", SOURCE) != state["source_id"]:
        raise RuntimeError("Source identity changed before HBA restoration")
    original = Path(state["source_hba_backup"]).read_bytes()
    inplace_source_hba(state, helper, original)
    reload_source_hba(commands, helper, state["source_hba_sha256"])


def freeze(args, helper, commands, work):
    """Reject new host clients, drain existing work, then disconnect the source bridge."""
    verify_validation_gate(args, helper)
    prior = read_preflight(args)
    source = inspect_private(commands, SOURCE, work / "source-before.private.json")
    networks = source["NetworkSettings"]["Networks"]
    if (
        source["Id"] != prior["source_id"]
        or helper.source_identity(commands) != prior["source_identity"]
        or set(networks) != {SOURCE_NETWORK}
        or networks[SOURCE_NETWORK]["IPAddress"] != SOURCE_IP
        or set(networks[SOURCE_NETWORK]["Aliases"]) != SOURCE_ALIASES
        or source["HostConfig"]["RestartPolicy"]["Name"] != "unless-stopped"
        or source["HostConfig"]["PortBindings"]
        != {"5432/tcp": [{"HostIp": "192.168.150.101", "HostPort": "5432"}]}
        or not any(
            m["Type"] == "bind"
            and m["Source"] == str(SOURCE_HBA)
            and m["Destination"] == "/etc/postgresql/pg_hba.conf"
            and not m["RW"]
            for m in source["Mounts"]
        )
    ):
        raise RuntimeError("Source identity, endpoint, HBA bind, or restart policy changed")
    fd = os.open(SOURCE_HBA, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        original = stream.read()
    if not original or original == MAINTENANCE_HBA:
        raise RuntimeError("Original source HBA is empty or already maintenance")
    sensitive_before = helper.sensitive_state(commands)
    backup = work / "source-hba-original.private.conf"
    fd = os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(original)
        stream.flush()
        os.fsync(stream.fileno())
    directory = os.open(work, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)
    if (
        helper.digest(backup)
        != commands.run(
            "docker", "exec", SOURCE, "sha256sum", "/etc/postgresql/pg_hba.conf"
        ).split()[0]
    ):
        raise RuntimeError("Original source HBA host/container bytes differ")
    state = {
        "status": "FREEZE_HBA_WRITE_PENDING",
        "source_id": prior["source_id"],
        "preflight": str(args.preflight),
        "source_network": SOURCE_NETWORK,
        "source_ip": SOURCE_IP,
        "source_aliases": sorted(SOURCE_ALIASES),
        "private_work": str(work),
        "source_hba_path": str(SOURCE_HBA),
        "source_hba_backup": str(backup),
        "source_hba_sha256": helper.digest(backup),
        "source_hba_device": info.st_dev,
        "source_hba_inode": info.st_ino,
        "source_hba_uid": info.st_uid,
        "source_hba_gid": info.st_gid,
        "source_hba_mode": info.st_mode & 0o7777,
        "sensitive_before": sensitive_before,
    }
    write_freeze_journal(args.output, state, create=True)
    try:
        inplace_source_hba(state, helper, MAINTENANCE_HBA)
        state["status"] = "FREEZE_HBA_RELOAD_PENDING"
        write_freeze_journal(args.output, state)
        import hashlib

        maintenance_sha = hashlib.sha256(MAINTENANCE_HBA).hexdigest()
        reload_source_hba(commands, helper, maintenance_sha)
        verify_maintenance(
            commands,
            {"hba_directory": str(SOURCE_HBA.parent), "maintenance_hba_sha256": maintenance_sha},
            helper,
        )
        state["status"] = "FREEZE_DRAIN_CHECK"
        write_freeze_journal(args.output, state)
        state["before"] = source_quiescence(helper, commands)
        state["status"] = "FREEZE_DISCONNECT_PENDING"
        write_freeze_journal(args.output, state)
        commands.run("docker", "network", "disconnect", SOURCE_NETWORK, SOURCE)
        state["status"] = "FREEZE_HBA_RESTORE_PENDING"
        write_freeze_journal(args.output, state)
        restore_source_hba(state, helper, commands)
        state["status"] = "FREEZE_DISCONNECTED_UNVERIFIED"
        write_freeze_journal(args.output, state)
        state["after"] = verify_fenced(helper, commands, work, prior)
        if (
            helper.sensitive_state(commands) != state["sensitive_before"]
            or state["after"]["databases"] != state["before"]["databases"]
        ):
            raise RuntimeError("Source data, roles or configuration changed during freeze")
        state["status"] = "SOURCE_FENCED"
    except (RuntimeError, OSError, ValueError) as error:
        state["failure"] = str(error)
        try:
            state["status"] = "FREEZE_HBA_RESTORE_PENDING"
            write_freeze_journal(args.output, state)
            restore_source_hba(state, helper, commands)
            current = inspect_private(commands, SOURCE, work / "freeze-error.private.json")
            if current["Id"] != prior["source_id"]:
                raise RuntimeError("Source identity changed during freeze recovery")
            state["status"] = (
                "FREEZE_ABORTED_SOURCE_RESTORED"
                if current["NetworkSettings"]["Networks"]
                else "FREEZE_DISCONNECTED_UNVERIFIED"
            )
        except (RuntimeError, OSError, ValueError) as recovery_error:
            state["recovery_failure"] = str(recovery_error)
    finally:
        write_freeze_journal(args.output, {**state, "commands": commands.events})
    return state


def final_backup(args, helper, commands, work):
    """Create a final backup only while the source fence remains established."""
    prior = read_preflight(args)
    freeze_state = json.loads(args.receipt.read_text(encoding="utf-8"))
    if freeze_state["status"] != "SOURCE_FENCED" or freeze_state["source_id"] != prior["source_id"]:
        raise RuntimeError("Matching successful freeze receipt required")
    verify_fenced(helper, commands, work, prior)
    backup_output = work / "final-backup.private.json"
    backup_args = argparse.Namespace(
        backup_root=args.backup_dir, output=backup_output, command_timeout=90, dump_timeout=600
    )
    if helper.backup(backup_args) != 0:
        raise RuntimeError("Final backup failed; its evidence and resources are retained")
    result = json.loads(backup_output.read_text(encoding="utf-8"))
    verify_fenced(helper, commands, work, prior)
    directory = Path(result["backup_directory"])
    manifest = verify_backup(helper, directory)
    if result["sensitive_before"] != freeze_state["sensitive_before"]:
        raise RuntimeError("Final backup roles or configuration differ from pre-freeze source")
    for database in DATABASES:
        snapshot = helper.Snapshot(commands, SOURCE, database, "agent_bootstrap")
        try:
            if helper.inventory(snapshot) != manifest["databases"][database]:
                raise RuntimeError("Source differs from final backup inventory: " + database)
        finally:
            snapshot.close()
    return {
        "status": "FINAL_BACKUP_REQUIRES_OFFSITE_VERIFICATION",
        "freeze_receipt": str(args.receipt),
        "backup_directory": str(directory),
        "backup_token": manifest["token"],
        "source_id": prior["source_id"],
    }


def rollback_freeze(args, helper, commands, work):
    """Restore original HBA and reconnect only if the reviewed source is disconnected."""
    prior = read_preflight(args)
    state = json.loads(args.receipt.read_text(encoding="utf-8"))
    if state["source_id"] != prior["source_id"] or state["status"] not in (
        "SOURCE_FENCED",
        "FREEZE_DISCONNECTED_UNVERIFIED",
        "FREEZE_DISCONNECT_PENDING",
        "FREEZE_HBA_WRITE_PENDING",
        "FREEZE_HBA_RELOAD_PENDING",
        "FREEZE_DRAIN_CHECK",
        "FREEZE_HBA_RESTORE_PENDING",
        "FREEZE_ABORTED_SOURCE_RESTORED",
    ):
        raise RuntimeError("Matching freeze journal required")
    if state["source_hba_path"] != str(SOURCE_HBA):
        raise RuntimeError("Freeze journal HBA path differs from reviewed source bind")
    source = inspect_private(commands, SOURCE, work / "source-rollback.private.json")
    endpoints = source["NetworkSettings"]["Networks"]
    if (
        source["Id"] != prior["source_id"]
        or not source["State"]["Running"]
        or (
            endpoints
            and (
                set(endpoints) != {SOURCE_NETWORK}
                or endpoints[SOURCE_NETWORK]["IPAddress"] != SOURCE_IP
                or set(endpoints[SOURCE_NETWORK]["Aliases"]) != SOURCE_ALIASES
            )
        )
    ):
        raise RuntimeError("Source identity or network differs from reviewed original")
    restore_source_hba(state, helper, commands)
    if not endpoints:
        commands.run(
            "docker",
            "network",
            "connect",
            "--ip",
            SOURCE_IP,
            "--alias",
            "postgres",
            "--alias",
            SOURCE,
            SOURCE_NETWORK,
            SOURCE,
        )
    source = inspect_private(commands, SOURCE, work / "source-reconnected.private.json")
    endpoints = source["NetworkSettings"]["Networks"]
    if (
        set(endpoints) != {SOURCE_NETWORK}
        or endpoints[SOURCE_NETWORK]["IPAddress"] != SOURCE_IP
        or set(endpoints[SOURCE_NETWORK]["Aliases"]) != SOURCE_ALIASES
    ):
        raise RuntimeError("Reconnected endpoint differs; manual review required")
    return {
        "status": "ORIGINAL_NETWORK_RECONNECTED",
        "source_id": prior["source_id"],
        "source_hba_sha256": state["source_hba_sha256"],
    }


COMPOSE_PATH = Path("/home/white7/agent-engine-demo-db/compose.yaml")
MAINTENANCE_HBA = b"local all all trust\nhost all all 0.0.0.0/0 reject\nhost all all ::/0 reject\n"


def read_final(args, helper, prior):
    state = json.loads(args.final_receipt.read_text(encoding="utf-8"))
    token = state["token"]
    if (
        state["status"] != "FINAL_RESTORE_VERIFIED"
        or len(token) != 12
        or any(c not in "0123456789abcdef" for c in token)
        or state["container"] != "pg1712-final-" + token
        or state["volume"] != "pg1712-final-data-" + token
        or state["network"] != "pg1712-final-net-" + token
        or state["image_id"] != prior["image_id"]
        or state["backup_dir"] != str(args.backup_dir)
    ):
        raise RuntimeError("Matching isolated final restore receipt required")
    manifest = verify_backup(helper, args.backup_dir)
    return state, manifest


def replace_once(text, before, after):
    if text.count(before) != 1:
        raise RuntimeError("Original compose differs from the reviewed layout")
    return text.replace(before, after, 1)


def stage_compose(args, helper, commands, work):
    """Prepare and validate a separate Compose project without touching the source."""
    prior = read_preflight(args)
    final, manifest = read_final(args, helper, prior)
    verify_fenced(helper, commands, work, prior)
    final_container = inspect_private(
        commands, final["container"], work / "final-inspect.private.json"
    )
    if (
        final_container["Image"] != prior["image_id"]
        or not final_container["State"]["Running"]
        or final_container["Config"]["Labels"].get(LABEL) != final["token"]
        or final_container["HostConfig"]["PortBindings"]
        or set(final_container["NetworkSettings"]["Networks"]) != {final["network"]}
        or not any(
            m["Type"] == "volume" and m["Name"] == final["volume"] and m["Destination"] == ROOT_DATA
            for m in final_container["Mounts"]
        )
    ):
        raise RuntimeError("Final restore container identity or isolation differs")
    for kind in ("volume", "network"):
        obj = json.loads(commands.run("docker", kind, "inspect", final[kind]))[0]
        if obj["Name"] != final[kind] or obj["Labels"].get(LABEL) != final["token"]:
            raise RuntimeError("Final volume or network identity differs")
        if kind == "network" and not obj["Internal"]:
            raise RuntimeError("Final restore network is not internal")
    if helper.digest(COMPOSE_PATH) != helper.digest(args.compose_backup):
        raise RuntimeError("Production compose differs from private original backup")
    original = COMPOSE_PATH.read_text(encoding="utf-8")
    tag = "pg1712-upgrade:final-" + final["token"]
    current_id = commands.run("docker", "image", "inspect", "--format", "{{.Id}}", prior["image"])
    if current_id != prior["image_id"]:
        raise RuntimeError("Reviewed target image tag changed")
    hba_dir = work / "hba"
    hba_dir.mkdir(mode=0o700)
    os.chown(hba_dir, 999, 999)
    hba = hba_dir / "pg_hba.conf"
    hba.write_bytes(MAINTENANCE_HBA)
    os.chown(hba, 999, 999)
    os.chmod(hba, 0o600)
    config_map = dict(
        zip(
            manifest["configuration_paths"],
            sorted((args.backup_dir / "private/config").glob("*.conf")),
            strict=True,
        )
    )
    source_hba = config_map["/etc/postgresql/pg_hba.conf"]
    staged = replace_once(
        original, "name: agent-engine-demo-db\n", "name: agent-engine-demo-db-v2\n"
    )
    old_image = (
        "    image: postgres:17.6-bookworm@sha256:"
        "f3bd19c606e442c3d7bdfa8002e03fe260a1023351e0ea4598032022b68dd6e3\n"
    )
    staged = replace_once(
        staged,
        old_image,
        f"    image: {tag}\n    pull_policy: never\n    container_name: {SOURCE}\n"
        f"    labels:\n      {LABEL}: '{final['token']}'\n",
    )
    staged = replace_once(
        staged,
        "      - agent_pg17:/var/lib/postgresql/data\n",
        "      - agent_pg17:/var/lib/postgresql/data\n",
    )
    staged = replace_once(
        staged,
        "      - ./pg_hba.conf:/etc/postgresql/pg_hba.conf:ro\n",
        f"      - {hba_dir}:/etc/postgresql:ro\n",
    )
    # The staged file is outside the original compose directory, so preserve
    # the original init-script bind with an absolute path in both locations.
    staged = replace_once(
        staged,
        "      - ./init-databases.sh:/docker-entrypoint-initdb.d/01-databases.sh:ro\n",
        f"      - {COMPOSE_PATH.parent / 'init-databases.sh'}:"
        "/docker-entrypoint-initdb.d/01-databases.sh:ro\n",
    )
    staged = replace_once(
        staged,
        "    healthcheck:\n",
        f"    networks:\n      original:\n        ipv4_address: {SOURCE_IP}\n"
        f"        aliases: [postgres, {SOURCE}]\n    healthcheck:\n",
    )
    staged = replace_once(
        staged,
        "volumes:\n  agent_pg17:\n",
        f"volumes:\n  agent_pg17:\n    external: true\n    name: {final['volume']}\n"
        f"networks:\n  original:\n    external: true\n    name: {SOURCE_NETWORK}\n",
    )
    staged_path = work / "compose.staged.private.yaml"
    staged_path.write_text(staged, encoding="utf-8")
    commands.run("docker", "image", "tag", prior["image_id"], tag)
    if commands.run("docker", "image", "inspect", "--format", "{{.Id}}", tag) != prior["image_id"]:
        raise RuntimeError("New local image tag differs from reviewed immutable ID")
    config_path = work / "compose.resolved.private.json"
    commands.run(
        "docker",
        "compose",
        "--project-directory",
        str(COMPOSE_PATH.parent),
        "-f",
        str(staged_path),
        "config",
        "--format",
        "json",
        output=config_path,
        private=True,
    )
    resolved = json.loads(config_path.read_text(encoding="utf-8"))
    service = resolved["services"]["postgres"]
    source_inspect = json.loads(Path(prior["private_source_inspect"]).read_text(encoding="utf-8"))[
        0
    ]
    mounts = {item["target"]: item for item in service["volumes"]}
    ports = service["ports"]
    if (
        resolved["name"] != "agent-engine-demo-db-v2"
        or service["container_name"] != SOURCE
        or service["image"] != tag
        or service["restart"] != "unless-stopped"
        or service["pull_policy"] != "never"
        or service["command"] != source_inspect["Config"]["Cmd"]
        or mounts[ROOT_DATA]["type"] != "volume"
        or mounts[ROOT_DATA]["source"] != "agent_pg17"
        or mounts["/etc/postgresql"]["source"] != str(hba_dir)
        or mounts["/etc/postgresql"].get("read_only") is not True
        or mounts["/docker-entrypoint-initdb.d/01-databases.sh"]["source"]
        != str(COMPOSE_PATH.parent / "init-databases.sh")
        or len(ports) != 1
        or ports[0]["host_ip"] != "192.168.150.101"
        or str(ports[0]["published"]) != "5432"
        or ports[0]["target"] != 5432
        or service["networks"]["original"]["ipv4_address"] != SOURCE_IP
        or not SOURCE_ALIASES.issubset(set(service["networks"]["original"]["aliases"]))
        or resolved["volumes"]["agent_pg17"]["name"] != final["volume"]
        or resolved["networks"]["original"]["name"] != SOURCE_NETWORK
    ):
        raise RuntimeError("Resolved staged compose differs from intended target")
    return {
        "status": "COMPOSE_STAGED_FOR_REVIEW",
        "token": final["token"],
        "final_receipt": str(args.final_receipt),
        "final_receipt_sha256": helper.digest(args.final_receipt),
        "source_id": prior["source_id"],
        "final_volume": final["volume"],
        "final_container": final["container"],
        "image_id": prior["image_id"],
        "image_tag": tag,
        "compose_original_sha256": helper.digest(COMPOSE_PATH),
        "compose_uid": COMPOSE_PATH.stat().st_uid,
        "compose_gid": COMPOSE_PATH.stat().st_gid,
        "compose_mode": COMPOSE_PATH.stat().st_mode & 0o777,
        "compose_backup": str(args.compose_backup),
        "staged_compose": str(staged_path),
        "staged_compose_sha256": helper.digest(staged_path),
        "hba_directory": str(hba_dir),
        "maintenance_hba_sha256": helper.digest(hba),
        "source_hba": str(source_hba),
        "source_hba_sha256": helper.digest(source_hba),
        "archive_name": SOURCE + "-pg176-" + final["token"],
        "private_work": str(work),
    }


def read_stage(args, helper, prior):
    staged = json.loads(args.stage_receipt.read_text(encoding="utf-8"))
    final, manifest = read_final(args, helper, prior)
    configs = dict(
        zip(
            manifest["configuration_paths"],
            sorted((args.backup_dir / "private/config").glob("*.conf")),
            strict=True,
        )
    )
    if (
        staged["status"] != "COMPOSE_STAGED_FOR_REVIEW"
        or staged["token"] != final["token"]
        or staged["source_id"] != prior["source_id"]
        or staged["final_volume"] != final["volume"]
        or staged["final_container"] != final["container"]
        or staged["image_id"] != prior["image_id"]
        or staged["archive_name"] != SOURCE + "-pg176-" + final["token"]
        or Path(staged["hba_directory"]) != Path(staged["private_work"]) / "hba"
        or Path(staged["staged_compose"])
        != Path(staged["private_work"]) / "compose.staged.private.yaml"
        or Path(staged["source_hba"]) != configs["/etc/postgresql/pg_hba.conf"]
        or staged["final_receipt_sha256"] != helper.digest(args.final_receipt)
        or staged["staged_compose_sha256"] != helper.digest(Path(staged["staged_compose"]))
        or staged["source_hba_sha256"] != helper.digest(Path(staged["source_hba"]))
        or staged["compose_original_sha256"] != helper.digest(Path(staged["compose_backup"]))
    ):
        raise RuntimeError("Staged compose identity or retained files changed")
    return staged, final, manifest


def atomic_file(path, data, mode, uid=None, gid=None):
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    with os.fdopen(fd, "wb") as stream:
        os.fchmod(stream.fileno(), mode)
        if uid is not None:
            os.fchown(stream.fileno(), uid, gid)
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def check_target(commands, work, staged, prior):
    target = inspect_private(commands, SOURCE, work / (uuid.uuid4().hex + ".private.json"))
    endpoints = target["NetworkSettings"]["Networks"]
    if (
        not target["State"]["Running"]
        or target["Image"] != prior["image_id"]
        or target["Config"]["Labels"].get(LABEL) != staged["token"]
        or set(endpoints) != {SOURCE_NETWORK}
        or endpoints[SOURCE_NETWORK]["IPAddress"] != SOURCE_IP
        or not SOURCE_ALIASES.issubset(set(endpoints[SOURCE_NETWORK]["Aliases"]))
        or target["HostConfig"]["PortBindings"]
        != {"5432/tcp": [{"HostIp": "192.168.150.101", "HostPort": "5432"}]}
        or not any(
            m["Type"] == "volume"
            and m["Name"] == staged["final_volume"]
            and m["Destination"] == ROOT_DATA
            for m in target["Mounts"]
        )
        or not any(
            m["Type"] == "bind"
            and m["Source"] == staged["hba_directory"]
            and m["Destination"] == "/etc/postgresql"
            and not m["RW"]
            for m in target["Mounts"]
        )
    ):
        raise RuntimeError("Published target identity, mount or endpoint differs")
    return target


def wait_sql(commands, container):
    deadline = time.monotonic() + 60
    while True:
        try:
            db_sql(commands, container, "postgres", "SELECT 1")
            return
        except RuntimeError:
            if time.monotonic() >= deadline:
                raise RuntimeError("Target startup deadline exceeded") from None
            time.sleep(1)


def verify_target_baseline(helper, commands, manifest, backup_dir):
    if db_sql(commands, SOURCE, "postgres", "SHOW server_version_num") != "170012":
        raise RuntimeError("Target server version differs")
    if db_sql(commands, SOURCE, "postgres", "SHOW shared_preload_libraries"):
        raise RuntimeError("Target preload differs")
    packages = commands.run(
        "docker",
        "exec",
        SOURCE,
        "dpkg-query",
        "-W",
        "postgresql-17",
        "postgresql-client-17",
        "postgresql-17-pgvector",
    ).splitlines()
    expected = {"postgresql-17": PG, "postgresql-client-17": PG, "postgresql-17-pgvector": VECTOR}
    if dict(line.split("\t", 1) for line in packages) != expected:
        raise RuntimeError("Target package versions differ")
    so = commands.run(
        "docker", "exec", SOURCE, "sha256sum", "/usr/lib/postgresql/17/lib/vector.so"
    ).split()[0]
    if so != VECTOR_SO_SHA:
        raise RuntimeError("Target vector binary differs")
    config_map = dict(
        zip(
            manifest["configuration_paths"],
            sorted((backup_dir / "private/config").glob("*.conf")),
            strict=True,
        )
    )
    for source_path, backed_up in config_map.items():
        if source_path == "/etc/postgresql/pg_hba.conf":
            continue  # Maintenance HBA is verified separately until writes open.
        actual = commands.run("docker", "exec", SOURCE, "sha256sum", source_path).split()[0]
        if actual != helper.digest(backed_up):
            raise RuntimeError("Target PostgreSQL configuration differs: " + source_path)
    if (
        db_sql(
            commands,
            SOURCE,
            "postgres",
            "SELECT count(*) FROM pg_file_settings WHERE error IS NOT NULL",
        )
        != "0"
    ):
        raise RuntimeError("Target PostgreSQL configuration contains errors")
    for database in DATABASES:
        snap = helper.Snapshot(commands, SOURCE, database, "agent_bootstrap")
        try:
            if helper.inventory(snap) != manifest["databases"][database]:
                raise RuntimeError("Target inventory or migration checksums differ: " + database)
        finally:
            snap.close()


def verify_maintenance(commands, staged, helper):
    path = Path(staged["hba_directory"]) / "pg_hba.conf"
    if (
        path.read_bytes() != MAINTENANCE_HBA
        or helper.digest(path) != staged["maintenance_hba_sha256"]
    ):
        raise RuntimeError("Maintenance HBA on host differs")
    actual = commands.run(
        "docker", "exec", SOURCE, "sha256sum", "/etc/postgresql/pg_hba.conf"
    ).split()[0]
    if actual != staged["maintenance_hba_sha256"]:
        raise RuntimeError("Target did not mount maintenance HBA")
    rules = json.loads(
        db_sql(
            commands,
            SOURCE,
            "postgres",
            "SELECT json_agg(json_build_array(type,database,user_name,address,"
            "auth_method,error) ORDER BY rule_number) FROM pg_hba_file_rules",
        )
    )
    if (
        len(rules) != 3
        or rules[0][0] != "local"
        or rules[0][4] != "trust"
        or rules[1][0] != "host"
        or rules[1][3] != "0.0.0.0"
        or rules[1][4] != "reject"
        or rules[2][0] != "host"
        or rules[2][3] != "::"
        or rules[2][4] != "reject"
        or any(rule[1] != ["all"] or rule[2] != ["all"] or rule[5] is not None for rule in rules)
    ):
        raise RuntimeError("Maintenance HBA parsed rules differ")
    # Issue a real PostgreSQL startup over the published TCP address; no password is sent.
    import struct

    packet = b"user\0agent_bootstrap\0database\0postgres\0\0"
    packet = struct.pack("!II", len(packet) + 8, 196608) + packet
    with socket.create_connection(("192.168.150.101", 5432), timeout=5) as sock:
        sock.settimeout(5)
        sock.sendall(packet)
        header = sock.recv(5, socket.MSG_WAITALL)
        if len(header) != 5 or header[0:1] != b"E":
            raise RuntimeError("Maintenance HBA did not reject TCP startup")
        size = struct.unpack("!I", header[1:])[0]
        payload = sock.recv(size - 4, socket.MSG_WAITALL)
        if len(payload) != size - 4 or b"C28000\0" not in payload:
            raise RuntimeError("TCP rejection is not PostgreSQL authentication denial")


def cutover(args, helper, commands, work):
    """Publish the final volume under maintenance HBA, retaining the original container."""
    prior = read_preflight(args)
    staged, final, manifest = read_stage(args, helper, prior)
    verify_fenced(helper, commands, work, prior)
    if helper.digest(COMPOSE_PATH) != staged["compose_original_sha256"]:
        raise RuntimeError("Original compose changed since review")
    if (
        commands.run("docker", "image", "inspect", "--format", "{{.Id}}", staged["image_tag"])
        != prior["image_id"]
    ):
        raise RuntimeError("Staged target image tag changed")
    if Path(staged["hba_directory"], "pg_hba.conf").read_bytes() != MAINTENANCE_HBA:
        raise RuntimeError("Maintenance HBA changed")
    if Path(staged["hba_directory"], "writes-opened.journal").exists():
        raise RuntimeError("This target already crossed or attempted the write boundary")
    isolated = inspect_private(commands, final["container"], work / "isolated-before.private.json")
    if (
        isolated["Image"] != prior["image_id"]
        or not isolated["State"]["Running"]
        or isolated["Config"]["Labels"].get(LABEL) != staged["token"]
        or isolated["HostConfig"]["PortBindings"]
        or set(isolated["NetworkSettings"]["Networks"]) != {final["network"]}
        or not any(
            m["Type"] == "volume" and m["Name"] == final["volume"] and m["Destination"] == ROOT_DATA
            for m in isolated["Mounts"]
        )
    ):
        raise RuntimeError("Isolated final target differs from reviewed volume")
    users = commands.run(
        "docker", "ps", "--filter", "volume=" + final["volume"], "--format", "{{.Names}}"
    ).splitlines()
    if users != [final["container"]]:
        raise RuntimeError("Final volume has unexpected running container users")
    state = {
        "status": "CUTOVER_PREPARED",
        "token": staged["token"],
        "source_id": prior["source_id"],
        "stage_receipt": str(args.stage_receipt),
        "stage_receipt_sha256": helper.digest(args.stage_receipt),
        "archive_name": staged["archive_name"],
        "final_container": final["container"],
        "private_work": str(work),
        "write_boundary_opened": False,
    }
    write_freeze_journal(args.output, state, create=True)
    try:
        commands.run("docker", "stop", final["container"])
        state["status"] = "CUTOVER_FINAL_STOPPED"
        write_freeze_journal(args.output, state)
        commands.run("docker", "stop", SOURCE)
        state["status"] = "CUTOVER_SOURCE_STOPPED"
        write_freeze_journal(args.output, state)
        commands.run("docker", "rename", SOURCE, staged["archive_name"])
        state["status"] = "CUTOVER_SOURCE_ARCHIVED"
        write_freeze_journal(args.output, state)
        if helper.digest(COMPOSE_PATH) != staged["compose_original_sha256"]:
            raise RuntimeError("Original compose changed before replacement")
        atomic_file(
            COMPOSE_PATH,
            Path(staged["staged_compose"]).read_bytes(),
            staged["compose_mode"],
            staged["compose_uid"],
            staged["compose_gid"],
        )
        state["status"] = "CUTOVER_COMPOSE_REPLACED"
        state["published_compose_sha256"] = helper.digest(COMPOSE_PATH)
        write_freeze_journal(args.output, state)
        commands.run(
            "docker",
            "compose",
            "--project-directory",
            str(COMPOSE_PATH.parent),
            "-f",
            str(COMPOSE_PATH),
            "up",
            "-d",
            "--no-deps",
            "--no-build",
            "--pull",
            "never",
            "postgres",
            timeout=120,
        )
        state["status"] = "CUTOVER_TARGET_STARTING"
        write_freeze_journal(args.output, state)
        wait_sql(commands, SOURCE)
        target = check_target(commands, work, staged, prior)
        verify_maintenance(commands, staged, helper)
        verify_target_baseline(helper, commands, manifest, args.backup_dir)
        expected = json.loads(
            (args.backup_dir / "private/globals-normalized.private.json").read_text(
                encoding="utf-8"
            )
        )
        if helper.normalized_globals(commands, SOURCE) != expected:
            raise RuntimeError("Published target globals differ")
        archived = inspect_private(commands, staged["archive_name"], work / "archived.private.json")
        if archived["Id"] != prior["source_id"] or archived["State"]["Running"]:
            raise RuntimeError("Original source archive identity differs")
        state.update(
            status="CUTOVER_MAINTENANCE_VERIFIED",
            target_id=target["Id"],
            inventory_equal=True,
            globals_match=True,
            maintenance_tcp_rejected=True,
        )
    except (RuntimeError, OSError, ValueError) as error:
        state["failure"] = str(error)
    finally:
        write_freeze_journal(args.output, {**state, "commands": commands.events})
    return state


def open_writes(args, helper, commands, work):
    """Record the irreversible boundary before loading the original host HBA rules."""
    prior = read_preflight(args)
    staged, _, _ = read_stage(args, helper, prior)
    cut = json.loads(args.cutover_receipt.read_text(encoding="utf-8"))
    if (
        cut["status"] != "CUTOVER_MAINTENANCE_VERIFIED"
        or cut["token"] != staged["token"]
        or cut["source_id"] != prior["source_id"]
        or cut["stage_receipt_sha256"] != helper.digest(args.stage_receipt)
    ):
        raise RuntimeError("Matching verified maintenance cutover required")
    target = check_target(commands, work, staged, prior)
    if (
        target["Id"] != cut["target_id"]
        or helper.digest(COMPOSE_PATH) != staged["staged_compose_sha256"]
    ):
        raise RuntimeError("Target or published compose changed")
    verify_maintenance(commands, staged, helper)
    hba_dir = Path(staged["hba_directory"])
    marker = hba_dir / "writes-opened.journal"
    state = {
        "status": "OPEN_WRITES_PREPARED",
        "token": staged["token"],
        "target_id": target["Id"],
        "cutover_receipt_sha256": helper.digest(args.cutover_receipt),
        "write_boundary_may_be_open": False,
    }
    write_freeze_journal(args.output, state, create=True)
    # This durable, exclusive marker disables automatic rollback even if the process crashes.
    write_freeze_journal(
        marker,
        {"token": staged["token"], "target_id": target["Id"], "status": "WRITES_MAY_OPEN"},
        create=True,
    )
    state.update(status="OPEN_WRITES_STARTED", write_boundary_may_be_open=True)
    write_freeze_journal(args.output, state)
    try:
        hba = hba_dir / "pg_hba.conf"
        atomic_file(hba, Path(staged["source_hba"]).read_bytes(), 0o600, 999, 999)
        if helper.digest(hba) != staged["source_hba_sha256"]:
            raise RuntimeError("Restored HBA host digest differs")
        mounted = commands.run(
            "docker", "exec", SOURCE, "sha256sum", "/etc/postgresql/pg_hba.conf"
        ).split()[0]
        if mounted != staged["source_hba_sha256"]:
            raise RuntimeError("Target did not observe the replacement HBA")
        before = db_sql(commands, SOURCE, "postgres", "SELECT pg_conf_load_time()")
        if db_sql(commands, SOURCE, "postgres", "SELECT pg_reload_conf()") != "t":
            raise RuntimeError("PostgreSQL rejected reload request")
        deadline = time.monotonic() + 30
        while db_sql(commands, SOURCE, "postgres", "SELECT pg_conf_load_time()") == before:
            if time.monotonic() >= deadline:
                raise RuntimeError("PostgreSQL did not report configuration reload")
            time.sleep(0.5)
        if (
            db_sql(
                commands,
                SOURCE,
                "postgres",
                "SELECT count(*) FROM pg_hba_file_rules WHERE error IS NOT NULL",
            )
            != "0"
        ):
            raise RuntimeError("Original HBA contains parse errors")
        if (
            db_sql(
                commands,
                SOURCE,
                "postgres",
                "SELECT count(*) FROM pg_file_settings WHERE error IS NOT NULL",
            )
            != "0"
        ):
            raise RuntimeError("PostgreSQL configuration reports reload errors")
        state.update(status="WRITES_OPEN_HBA_RELOADED", source_hba_sha256=mounted)
    except (RuntimeError, OSError, ValueError) as error:
        state["failure"] = str(error)
    finally:
        write_freeze_journal(args.output, {**state, "commands": commands.events})
    return state


def container_names(commands):
    return set(commands.run("docker", "ps", "-a", "--format", "{{.Names}}").splitlines())


def rollback_cutover(args, helper, commands, work):
    """Restore the original source only before the durable write-boundary marker."""
    prior = read_preflight(args)
    staged, _, _ = read_stage(args, helper, prior)
    cut = json.loads(args.cutover_receipt.read_text(encoding="utf-8"))
    if (
        cut["token"] != staged["token"]
        or cut["source_id"] != prior["source_id"]
        or cut["stage_receipt_sha256"] != helper.digest(args.stage_receipt)
        or not cut["status"].startswith("CUTOVER_")
        or cut.get("write_boundary_opened") is not False
    ):
        raise RuntimeError("Matching cutover recovery journal required")
    if (Path(staged["hba_directory"]) / "writes-opened.journal").exists():
        raise RuntimeError("Write boundary may have opened; automatic rollback is forbidden")
    if (Path(staged["hba_directory"]) / "pg_hba.conf").read_bytes() != MAINTENANCE_HBA:
        raise RuntimeError("Maintenance HBA differs; writes cannot be ruled out")
    state = {
        "status": "ROLLBACK_CUTOVER_STARTED",
        "token": staged["token"],
        "source_id": prior["source_id"],
        "cutover_receipt_sha256": helper.digest(args.cutover_receipt),
    }
    write_freeze_journal(args.output, state, create=True)
    try:
        names = container_names(commands)
        archived_name = staged["archive_name"]
        if SOURCE in names:
            named = inspect_private(commands, SOURCE, work / "named.private.json")
            if named["Id"] != prior["source_id"]:
                if (
                    not named["Id"]
                    or (cut.get("target_id") is not None and named["Id"] != cut["target_id"])
                    or named["Config"]["Labels"].get(LABEL) != staged["token"]
                    or named["Image"] != prior["image_id"]
                    or not any(
                        m["Type"] == "volume"
                        and m["Name"] == staged["final_volume"]
                        and m["Destination"] == ROOT_DATA
                        for m in named["Mounts"]
                    )
                    or not any(
                        m["Type"] == "bind"
                        and m["Source"] == staged["hba_directory"]
                        and m["Destination"] == "/etc/postgresql"
                        and not m["RW"]
                        for m in named["Mounts"]
                    )
                ):
                    raise RuntimeError("Container occupying source name is not reviewed target")
                if archived_name not in names:
                    raise RuntimeError("Original archived source is missing")
                archived = inspect_private(
                    commands, archived_name, work / "archive-before.private.json"
                )
                if archived["Id"] != prior["source_id"] or archived["State"]["Running"]:
                    raise RuntimeError("Original source archive differs")
                if named["State"]["Running"]:
                    commands.run("docker", "stop", named["Id"])
                retained_name = "pg1712-cutover-retained-" + staged["token"]
                if retained_name in names:
                    raise RuntimeError("Target archive name already exists")
                commands.run("docker", "rename", named["Id"], retained_name)
                state["retained_target"] = retained_name
                state["status"] = "ROLLBACK_TARGET_STOPPED"
                write_freeze_journal(args.output, state)
                names = container_names(commands)
        if SOURCE not in names:
            if archived_name not in names:
                raise RuntimeError("Original source archive not found")
            archived = inspect_private(commands, archived_name, work / "archive.private.json")
            if archived["Id"] != prior["source_id"] or archived["State"]["Running"]:
                raise RuntimeError("Original source archive identity or state differs")
            commands.run("docker", "rename", archived_name, SOURCE)
            state["status"] = "ROLLBACK_SOURCE_RENAMED"
            write_freeze_journal(args.output, state)
        original = inspect_private(commands, SOURCE, work / "original.private.json")
        saved = json.loads(Path(prior["private_source_inspect"]).read_text(encoding="utf-8"))[0]
        if (
            original["Id"] != prior["source_id"]
            or original["Image"] != saved["Image"]
            or sorted(original["Mounts"], key=lambda item: json.dumps(item, sort_keys=True))
            != sorted(saved["Mounts"], key=lambda item: json.dumps(item, sort_keys=True))
        ):
            raise RuntimeError("Original source image or mounts differ")
        actual_compose = helper.digest(COMPOSE_PATH)
        if actual_compose == staged["staged_compose_sha256"]:
            atomic_file(
                COMPOSE_PATH,
                Path(staged["compose_backup"]).read_bytes(),
                staged["compose_mode"],
                staged["compose_uid"],
                staged["compose_gid"],
            )
        elif actual_compose != staged["compose_original_sha256"]:
            raise RuntimeError("Production compose changed; manual review required")
        if helper.digest(COMPOSE_PATH) != staged["compose_original_sha256"]:
            raise RuntimeError("Original compose restoration failed")
        state["status"] = "ROLLBACK_COMPOSE_RESTORED"
        write_freeze_journal(args.output, state)
        if not original["State"]["Running"]:
            commands.run("docker", "start", SOURCE)
        original = inspect_private(commands, SOURCE, work / "source-started.private.json")
        endpoints = original["NetworkSettings"]["Networks"]
        if not endpoints:
            commands.run(
                "docker",
                "network",
                "connect",
                "--ip",
                SOURCE_IP,
                "--alias",
                "postgres",
                "--alias",
                SOURCE,
                SOURCE_NETWORK,
                SOURCE,
            )
        original = inspect_private(commands, SOURCE, work / "source-reconnected.private.json")
        endpoints = original["NetworkSettings"]["Networks"]
        if (
            set(endpoints) != {SOURCE_NETWORK}
            or endpoints[SOURCE_NETWORK]["IPAddress"] != SOURCE_IP
            or set(endpoints[SOURCE_NETWORK]["Aliases"]) != SOURCE_ALIASES
        ):
            raise RuntimeError("Original source network restoration differs")
        wait_sql(commands, SOURCE)
        if db_sql(commands, SOURCE, "postgres", "SHOW server_version_num") != "170006":
            raise RuntimeError("Reconnected source version differs from PG17.6")
        state["status"] = "ROLLBACK_ORIGINAL_RESTORED"
    except (RuntimeError, OSError, ValueError) as error:
        state["failure"] = str(error)
    finally:
        write_freeze_journal(args.output, {**state, "commands": commands.events})
    return state


def stop_open_target(args, helper, commands, work):
    """After write opening, stop the target while retaining its data for manual review."""
    prior = read_preflight(args)
    staged, _, _ = read_stage(args, helper, prior)
    marker = Path(staged["hba_directory"]) / "writes-opened.journal"
    if not marker.exists():
        raise RuntimeError("Write-boundary marker absent; use pre-write rollback")
    boundary = json.loads(marker.read_text(encoding="utf-8"))
    target = check_target(commands, work, staged, prior)
    if boundary["token"] != staged["token"] or boundary["target_id"] != target["Id"]:
        raise RuntimeError("Target does not match write-boundary marker")
    state = {
        "status": "STOP_OPEN_TARGET_PENDING",
        "token": staged["token"],
        "target_id": target["Id"],
    }
    write_freeze_journal(args.output, state, create=True)
    try:
        commands.run("docker", "stop", SOURCE)
        state["status"] = "OPEN_TARGET_STOPPED_MANUAL_REVIEW"
    except (RuntimeError, OSError, ValueError) as error:
        state["failure"] = str(error)
    finally:
        write_freeze_journal(args.output, {**state, "commands": commands.events})
    return state


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "stage",
        choices=(
            "preflight",
            "restore",
            "resume-validation",
            "freeze",
            "final-backup",
            "rollback-freeze",
            "final-restore",
            "stage-compose",
            "cutover",
            "open-writes",
            "rollback-cutover",
            "stop-open-target",
        ),
    )
    parser.add_argument("--helper", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--backup-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--image")
    parser.add_argument("--minimum-free-bytes", type=int)
    parser.add_argument("--preflight", type=Path)
    parser.add_argument("--receipt", type=Path)
    parser.add_argument("--validation-gate", type=Path)
    parser.add_argument("--validation-receipt", type=Path)
    parser.add_argument("--windows-receipt", type=Path)
    parser.add_argument("--backup-receipt", type=Path)
    parser.add_argument("--final-receipt", type=Path)
    parser.add_argument("--stage-receipt", type=Path)
    parser.add_argument("--cutover-receipt", type=Path)
    parser.add_argument("--compose-backup", type=Path)
    parser.add_argument("--validation-port", type=int, default=56322)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Fresh evidence output required; retain prior attempts")
    formal = (
        "freeze",
        "final-backup",
        "final-restore",
        "rollback-freeze",
        "stage-compose",
        "cutover",
        "open-writes",
        "rollback-cutover",
        "stop-open-target",
    )
    if args.stage in formal and not FORMAL_EXECUTION_ENABLED:
        parser.error("Formal stages are disabled until independent QA and main review")
    if args.stage in formal:
        import fcntl

        lock_fd = os.open(args.workspace / ".pg1712-upgrade.lock", os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            parser.error("Another formal upgrade stage holds the workspace lock")
    if (
        args.stage
        in ("stage-compose", "cutover", "open-writes", "rollback-cutover", "stop-open-target")
        and args.final_receipt is None
    ):
        parser.error("This stage requires --final-receipt")
    if args.stage == "stage-compose" and args.compose_backup is None:
        parser.error("stage-compose requires --compose-backup")
    if (
        args.stage in ("cutover", "open-writes", "rollback-cutover", "stop-open-target")
        and args.stage_receipt is None
    ):
        parser.error("This stage requires --stage-receipt")
    if args.stage in ("open-writes", "rollback-cutover") and args.cutover_receipt is None:
        parser.error("This stage requires --cutover-receipt")
    if args.stage == "preflight" and (not args.image or args.minimum_free_bytes is None):
        parser.error("Explicit retained image and operator disk budget required")
    if args.stage != "preflight" and args.preflight is None:
        parser.error("Reviewed preflight evidence required")
    if args.stage == "freeze" and (args.validation_gate is None or args.validation_receipt is None):
        parser.error("freeze requires validation gate and matching validation receipt")
    if args.stage == "final-restore" and (
        args.windows_receipt is None
        or args.backup_receipt is None
        or args.minimum_free_bytes is None
    ):
        parser.error("final-restore requires Windows verification and remaining disk budget")
    if args.stage in ("final-backup", "rollback-freeze", "final-restore") and args.receipt is None:
        parser.error("This stage requires --receipt")
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
        stages = {
            "preflight": preflight,
            "restore": restore,
            "resume-validation": resume_validation,
            "freeze": freeze,
            "final-backup": final_backup,
            "final-restore": restore,
            "rollback-freeze": rollback_freeze,
            "stage-compose": stage_compose,
            "cutover": cutover,
            "open-writes": open_writes,
            "rollback-cutover": rollback_cutover,
            "stop-open-target": stop_open_target,
        }
        result = stages[args.stage](args, helper, commands, work)
    except (RuntimeError, OSError, ValueError) as error:
        result = {"status": "FAILED_RETAINED", "failure": str(error)}
    result["upgrade_script_sha256"] = helper.digest(Path(__file__))
    result["private_work"] = str(work)
    result["commands"] = commands.events
    journal_stages = ("freeze", "cutover", "open-writes", "rollback-cutover", "stop-open-target")
    if args.stage in journal_stages:
        if result["status"] != "FAILED_RETAINED":
            write_freeze_journal(args.output, result)
        elif not args.output.exists():
            write_freeze_journal(args.output, result, create=True)
    else:
        helper.write_json(args.output, result)
    print(json.dumps({key: result.get(key) for key in ("status", "failure", "container", "ip")}))
    return (
        0
        if result["status"]
        in (
            "PREFLIGHT_OBSERVED_NOT_FENCED",
            "VALIDATION_READY_NO_CUTOVER",
            "SOURCE_FENCED",
            "FINAL_BACKUP_REQUIRES_OFFSITE_VERIFICATION",
            "ORIGINAL_NETWORK_RECONNECTED",
            "FINAL_RESTORE_VERIFIED",
            "COMPOSE_STAGED_FOR_REVIEW",
            "CUTOVER_MAINTENANCE_VERIFIED",
            "WRITES_OPEN_HBA_RELOADED",
            "ROLLBACK_ORIGINAL_RESTORED",
            "OPEN_TARGET_STOPPED_MANUAL_REVIEW",
        )
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
