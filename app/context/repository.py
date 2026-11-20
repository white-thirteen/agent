"""Archive records scoped by both columns of the trusted session identity."""

from app.context.models import Archive


class ArchiveRepository:
    def __init__(self, pool):
        self.pool = pool

    @staticmethod
    def _archive(identity, row):
        if row is None:
            return None
        return Archive(
            identity=identity,
            segment_id=row[0],
            archive_ref=row[1],
            message_ids=tuple(row[2]),
            content_hash=row[3],
            source_checkpoint_id=row[4],
            relative_path=row[5],
            file_hash=row[6],
            status=row[7],
        )

    async def prepare(self, archive, task_ids):
        identity = archive.identity
        async with self.pool.connection() as conn, conn.transaction():
            await conn.execute(
                "INSERT INTO context_archive(user_id,conversation_id,segment_id,archive_ref,"
                "message_ids,task_ids,content_hash,source_checkpoint_id,relative_path,status) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'PREPARING') ON CONFLICT DO NOTHING",
                (
                    identity.user_id,
                    identity.conversation_id,
                    archive.segment_id,
                    archive.archive_ref,
                    list(archive.message_ids),
                    list(task_ids),
                    archive.content_hash,
                    archive.source_checkpoint_id,
                    archive.relative_path,
                ),
            )
            row = await (
                await conn.execute(
                    "SELECT segment_id,archive_ref,message_ids,content_hash,source_checkpoint_id,"
                    "relative_path,file_hash,status,task_ids FROM context_archive "
                    "WHERE user_id=%s AND conversation_id=%s AND segment_id=%s FOR UPDATE",
                    (identity.user_id, identity.conversation_id, archive.segment_id),
                )
            ).fetchone()
            if row is None or (
                tuple(row[2]) != archive.message_ids
                or row[3] != archive.content_hash
                or row[1] != archive.archive_ref
                or row[5] != archive.relative_path
                or tuple(row[8]) != tuple(task_ids)
            ):
                raise ValueError("Archive range conflict")
            return self._archive(identity, row)

    async def ready(self, archive, file_hash):
        identity = archive.identity
        async with self.pool.connection() as conn, conn.transaction():
            row = await (
                await conn.execute(
                    "UPDATE context_archive SET status='READY',file_hash=%s "
                    "WHERE user_id=%s AND conversation_id=%s AND segment_id=%s "
                    "AND content_hash=%s AND (status='PREPARING' OR file_hash=%s) "
                    "RETURNING segment_id,archive_ref,message_ids,content_hash,"
                    "source_checkpoint_id,"
                    "relative_path,file_hash,status",
                    (
                        file_hash,
                        identity.user_id,
                        identity.conversation_id,
                        archive.segment_id,
                        archive.content_hash,
                        file_hash,
                    ),
                )
            ).fetchone()
            if row is None:
                raise ValueError("Archive publication conflict")
            return self._archive(identity, row)

    async def get(self, identity, archive_ref):
        async with self.pool.connection() as conn:
            row = await (
                await conn.execute(
                    "SELECT segment_id,archive_ref,message_ids,content_hash,source_checkpoint_id,"
                    "relative_path,file_hash,status FROM context_archive "
                    "WHERE user_id=%s AND conversation_id=%s AND archive_ref=%s AND status='READY'",
                    (identity.user_id, identity.conversation_id, archive_ref),
                )
            ).fetchone()
            return self._archive(identity, row)

    async def candidates(self, identity, *, limit, task_id=None, message_id=None, refs=()):
        async with self.pool.connection() as conn:
            rows = await (
                await conn.execute(
                    "SELECT segment_id,archive_ref,message_ids,content_hash,source_checkpoint_id,"
                    "relative_path,file_hash,status FROM context_archive "
                    "WHERE user_id=%s AND conversation_id=%s AND status='READY' "
                    "ORDER BY (archive_ref=ANY(%s)) DESC, (%s=ANY(task_ids)) DESC NULLS LAST, "
                    "(%s=ANY(message_ids)) DESC NULLS LAST, ordinal DESC LIMIT %s",
                    (
                        identity.user_id,
                        identity.conversation_id,
                        list(refs),
                        task_id,
                        message_id,
                        limit,
                    ),
                )
            ).fetchall()
            return [self._archive(identity, row) for row in rows]

    async def neighbors(self, identity, archive_ref, limit):
        async with self.pool.connection() as conn:
            rows = await (
                await conn.execute(
                    "SELECT segment_id,archive_ref,message_ids,content_hash,source_checkpoint_id,"
                    "relative_path,file_hash,status FROM context_archive WHERE user_id=%s "
                    "AND conversation_id=%s AND status='READY' AND ordinal IN ("
                    "SELECT ordinal FROM context_archive WHERE user_id=%s AND conversation_id=%s "
                    "AND status='READY' AND ordinal < (SELECT ordinal FROM context_archive "
                    "WHERE user_id=%s AND conversation_id=%s AND archive_ref=%s "
                    "AND status='READY') "
                    "ORDER BY ordinal DESC LIMIT 1) LIMIT %s",
                    (
                        identity.user_id,
                        identity.conversation_id,
                        identity.user_id,
                        identity.conversation_id,
                        identity.user_id,
                        identity.conversation_id,
                        archive_ref,
                        limit,
                    ),
                )
            ).fetchall()
            return [self._archive(identity, row) for row in rows]


class ContextRepository(ArchiveRepository):
    """Persist summaries and reserve each maintenance request before provider I/O."""

    async def register_maintenance(
        self,
        identity,
        *,
        maintenance_id,
        source_task_id,
        source_run_id,
        source_checkpoint_id,
        message_ids,
        content_hash,
        policy_version,
        budget_version,
        max_input_tokens,
        max_output_tokens,
        archive_refs,
    ):
        from psycopg.rows import dict_row

        if not all(
            (
                maintenance_id,
                source_task_id,
                source_run_id,
                source_checkpoint_id,
                message_ids,
                content_hash,
                policy_version,
                budget_version,
                archive_refs,
            )
        ):
            raise ValueError("Incomplete maintenance source")
        if max_output_tokens <= 0 or max_input_tokens <= max_output_tokens:
            raise ValueError("Invalid maintenance token limits")
        async with self.pool.connection() as conn, conn.transaction():
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    "INSERT INTO context_maintenance (maintenance_id,user_id,conversation_id,"
                    "source_task_id,source_run_id,source_checkpoint_id,message_ids,content_hash,"
                    "policy_version,budget_version,max_input_tokens,max_output_tokens,archive_refs,"
                    "deadline_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,"
                    "clock_timestamp() + interval '30 seconds') ON CONFLICT DO NOTHING",
                    (
                        maintenance_id,
                        identity.user_id,
                        identity.conversation_id,
                        source_task_id,
                        source_run_id,
                        source_checkpoint_id,
                        list(message_ids),
                        content_hash,
                        policy_version,
                        budget_version,
                        max_input_tokens,
                        max_output_tokens,
                        list(archive_refs),
                    ),
                )
                await cur.execute(
                    "SELECT *, extract(epoch from (deadline_at-clock_timestamp())) AS remaining "
                    "FROM context_maintenance WHERE user_id=%s AND conversation_id=%s "
                    "AND content_hash=%s AND policy_version=%s FOR UPDATE",
                    (identity.user_id, identity.conversation_id, content_hash, policy_version),
                )
                work = await cur.fetchone()
                if work is None:
                    raise ValueError("Maintenance ID conflict")
                if (
                    work["source_checkpoint_id"] != source_checkpoint_id
                    or work["message_ids"] != list(message_ids)
                    or work["archive_refs"] != list(archive_refs)
                    or work["budget_version"] != budget_version
                    or work["max_input_tokens"] != max_input_tokens
                    or work["max_output_tokens"] != max_output_tokens
                ):
                    raise ValueError("Maintenance source or budget conflict")
                return work

    async def maintenance(self, maintenance_id):
        from psycopg.rows import dict_row

        async with self.pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                "SELECT *, extract(epoch from (deadline_at-clock_timestamp())) AS remaining "
                "FROM context_maintenance WHERE maintenance_id=%s",
                (maintenance_id,),
            )
            return await cur.fetchone()

    async def claim_maintenance(self, maintenance_id, *, allow_exhausted=False):
        from uuid import uuid4

        claim_id = str(uuid4())
        async with self.pool.connection() as conn, conn.transaction():
            row = await (
                await conn.execute(
                    "UPDATE context_maintenance SET status='RUNNING',claim_id=%s "
                    "WHERE maintenance_id=%s AND (status IN ('PENDING','FAILED','INTERRUPTED') "
                    "OR (status='EXHAUSTED' AND %s)) RETURNING maintenance_id",
                    (claim_id, maintenance_id, allow_exhausted),
                )
            ).fetchone()
            if row is None:
                raise ValueError("Maintenance in progress or unavailable")
        return claim_id

    async def reserve_attempt(self, maintenance_id, claim_id):
        from uuid import uuid4

        attempt_id = str(uuid4())
        async with self.pool.connection() as conn, conn.transaction():
            row = await (
                await conn.execute(
                    "UPDATE context_maintenance SET reserved_attempts=reserved_attempts+1,"
                    "status='RUNNING' WHERE maintenance_id=%s AND claim_id=%s "
                    "AND reserved_attempts<2 AND deadline_at>clock_timestamp() "
                    "AND status='RUNNING' RETURNING maintenance_id",
                    (maintenance_id, claim_id),
                )
            ).fetchone()
            if row is None:
                raise ValueError("Maintenance budget exhausted or unavailable")
            await conn.execute(
                "INSERT INTO context_maintenance_attempt(attempt_id,maintenance_id,claim_id,"
                "status) "
                "VALUES (%s,%s,%s,'RESERVED')",
                (attempt_id, maintenance_id, claim_id),
            )
        return attempt_id

    async def record_attempt(self, maintenance_id, claim_id, attempt_id, usage):
        async with self.pool.connection() as conn, conn.transaction():
            row = await (
                await conn.execute(
                    "UPDATE context_maintenance_attempt SET status='RECORDED',input_tokens=%s,"
                    "output_tokens=%s,total_tokens=%s,usage_status=%s,estimation_method=%s "
                    "WHERE maintenance_id=%s AND claim_id=%s AND attempt_id=%s "
                    "AND status='RESERVED' "
                    "RETURNING attempt_id",
                    (
                        usage.input_tokens,
                        usage.output_tokens,
                        usage.total_tokens,
                        usage.status,
                        usage.estimation_method,
                        maintenance_id,
                        claim_id,
                        attempt_id,
                    ),
                )
            ).fetchone()
            if row is None:
                row = await (
                    await conn.execute(
                        "SELECT input_tokens,output_tokens,total_tokens,usage_status,"
                        "estimation_method "
                        "FROM context_maintenance_attempt WHERE maintenance_id=%s "
                        "AND claim_id=%s AND attempt_id=%s "
                        "AND status='RECORDED'",
                        (maintenance_id, claim_id, attempt_id),
                    )
                ).fetchone()
                if row != (
                    usage.input_tokens,
                    usage.output_tokens,
                    usage.total_tokens,
                    usage.status,
                    usage.estimation_method,
                ):
                    raise ValueError("Attempt receipt conflict")

    async def attempts(self, maintenance_id):
        from psycopg.rows import dict_row

        async with self.pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                "SELECT * FROM context_maintenance_attempt WHERE maintenance_id=%s "
                "ORDER BY attempt_id",
                (maintenance_id,),
            )
            return await cur.fetchall()

    async def maintenance_usage(self, maintenance_id):
        from app.runtime.model_gateway import UsageReport

        rows = await self.attempts(maintenance_id)
        status = (
            "unknown"
            if any(row["usage_status"] == "unknown" for row in rows)
            else "estimated"
            if any(row["usage_status"] == "estimated" for row in rows)
            else "known"
        )
        totals = []
        for field in ("input_tokens", "output_tokens", "total_tokens"):
            values = [row[field] for row in rows]
            totals.append(
                sum(values) if values and all(value is not None for value in values) else None
            )
        if not rows:
            status = "unknown"
        return sum(row["status"] == "RECORDED" for row in rows), UsageReport(*totals, status=status)

    async def interrupt_maintenance(self, maintenance_id):
        """Call only after exclusive session ownership proves the old executor is gone."""
        async with self.pool.connection() as conn, conn.transaction():
            row = await (
                await conn.execute(
                    "SELECT status FROM context_maintenance WHERE maintenance_id=%s FOR UPDATE",
                    (maintenance_id,),
                )
            ).fetchone()
            if row is None or row[0] != "RUNNING":
                return
            await conn.execute(
                "UPDATE context_maintenance_attempt SET status='INTERRUPTED' "
                "WHERE maintenance_id=%s AND status='RESERVED'",
                (maintenance_id,),
            )
            await conn.execute(
                "UPDATE context_maintenance SET status=CASE WHEN reserved_attempts>=2 OR "
                "deadline_at<=clock_timestamp() THEN 'EXHAUSTED' ELSE 'INTERRUPTED' END, "
                "claim_id=NULL "
                "WHERE maintenance_id=%s AND status='RUNNING'",
                (maintenance_id,),
            )

    async def finish_maintenance(self, maintenance_id, claim_id, *, summary_id=None):
        async with self.pool.connection() as conn, conn.transaction():
            row = await (
                await conn.execute(
                    "UPDATE context_maintenance SET summary_id=%s, "
                    "status=CASE WHEN %s::text IS NOT NULL "
                    "THEN 'SUCCEEDED' WHEN reserved_attempts>=2 OR deadline_at<=clock_timestamp() "
                    "THEN 'EXHAUSTED' ELSE 'FAILED' END, claim_id=NULL "
                    "WHERE maintenance_id=%s AND claim_id=%s AND status='RUNNING' "
                    "AND (%s::text IS NULL OR EXISTS (SELECT 1 FROM context_summary s "
                    "WHERE s.user_id=context_maintenance.user_id "
                    "AND s.conversation_id=context_maintenance.conversation_id "
                    "AND s.summary_id=%s AND s.archive_refs=context_maintenance.archive_refs "
                    "AND s.message_ids=context_maintenance.message_ids "
                    "AND s.source_checkpoint_id=context_maintenance.source_checkpoint_id "
                    "AND s.policy_version=context_maintenance.policy_version)) RETURNING status",
                    (summary_id, summary_id, maintenance_id, claim_id, summary_id, summary_id),
                )
            ).fetchone()
            if row is None:
                raise ValueError("Maintenance completion conflict")
            return row[0]

    @staticmethod
    def _summary(identity, row):
        from app.context.models import Summary

        if row is None:
            return None
        return Summary(
            identity=identity,
            summary_id=row[0],
            version=row[1],
            text=row[2],
            archive_refs=tuple(row[3]),
            message_ids=tuple(row[4]),
            parent_summary_id=row[5],
            input_hash=row[6],
            status="READY",
        )

    async def get_summary(self, identity, summary_id):
        async with self.pool.connection() as conn:
            row = await (
                await conn.execute(
                    "SELECT summary_id,version,text,archive_refs,message_ids,"
                    "parent_summary_id,input_hash "
                    "FROM context_summary WHERE user_id=%s AND conversation_id=%s "
                    "AND summary_id=%s",
                    (identity.user_id, identity.conversation_id, summary_id),
                )
            ).fetchone()
            return self._summary(identity, row)

    async def find_summary(
        self,
        identity,
        *,
        input_hash,
        version,
        source_checkpoint_id,
        policy_version,
        model_version,
        prompt_version,
    ):
        async with self.pool.connection() as conn:
            row = await (
                await conn.execute(
                    "SELECT summary_id,version,text,archive_refs,message_ids,"
                    "parent_summary_id,input_hash "
                    "FROM context_summary WHERE user_id=%s AND conversation_id=%s "
                    "AND input_hash=%s "
                    "AND version=%s AND source_checkpoint_id=%s AND policy_version=%s "
                    "AND model_version=%s AND prompt_version=%s",
                    (
                        identity.user_id,
                        identity.conversation_id,
                        input_hash,
                        version,
                        source_checkpoint_id,
                        policy_version,
                        model_version,
                        prompt_version,
                    ),
                )
            ).fetchone()
            return self._summary(identity, row)

    async def save_summary(
        self, summary, *, source_checkpoint_id, policy_version, model_version, prompt_version
    ):
        identity = summary.identity
        if (
            summary.status != "READY"
            or not summary.archive_refs
            or not summary.message_ids
            or len(set(summary.archive_refs)) != len(summary.archive_refs)
        ):
            raise ValueError("Invalid summary coverage")
        async with self.pool.connection() as conn, conn.transaction():
            covered_ids = []
            for ref in summary.archive_refs:
                row = await (
                    await conn.execute(
                        "SELECT message_ids FROM context_archive WHERE user_id=%s "
                        "AND conversation_id=%s "
                        "AND archive_ref=%s AND status='READY' FOR SHARE",
                        (identity.user_id, identity.conversation_id, ref),
                    )
                ).fetchone()
                if row is None:
                    raise ValueError("Summary archive unavailable")
                covered_ids.extend(row[0])
            if tuple(covered_ids) != summary.message_ids or len(set(covered_ids)) != len(
                covered_ids
            ):
                raise ValueError("Summary coverage does not match archives")
            if summary.parent_summary_id:
                parent = await (
                    await conn.execute(
                        "SELECT version,archive_refs,message_ids FROM context_summary "
                        "WHERE user_id=%s AND conversation_id=%s AND summary_id=%s FOR SHARE",
                        (identity.user_id, identity.conversation_id, summary.parent_summary_id),
                    )
                ).fetchone()
                if (
                    parent is None
                    or parent[0] >= summary.version
                    or tuple(parent[1]) != summary.archive_refs[: len(parent[1])]
                    or tuple(parent[2]) != summary.message_ids[: len(parent[2])]
                ):
                    raise ValueError("Invalid parent summary")
            await conn.execute(
                "INSERT INTO context_summary(user_id,conversation_id,summary_id,version,text,"
                "archive_refs,message_ids,parent_summary_id,input_hash,source_checkpoint_id,"
                "policy_version,model_version,prompt_version) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                (
                    identity.user_id,
                    identity.conversation_id,
                    summary.summary_id,
                    summary.version,
                    summary.text,
                    list(summary.archive_refs),
                    list(summary.message_ids),
                    summary.parent_summary_id,
                    summary.input_hash,
                    source_checkpoint_id,
                    policy_version,
                    model_version,
                    prompt_version,
                ),
            )
            row = await (
                await conn.execute(
                    "SELECT summary_id,version,text,archive_refs,message_ids,"
                    "parent_summary_id,input_hash "
                    "FROM context_summary WHERE user_id=%s AND conversation_id=%s "
                    "AND input_hash=%s "
                    "AND version=%s AND source_checkpoint_id=%s AND policy_version=%s "
                    "AND model_version=%s AND prompt_version=%s",
                    (
                        identity.user_id,
                        identity.conversation_id,
                        summary.input_hash,
                        summary.version,
                        source_checkpoint_id,
                        policy_version,
                        model_version,
                        prompt_version,
                    ),
                )
            ).fetchone()
            result = self._summary(identity, row)
            if (
                result is None
                or result.archive_refs != summary.archive_refs
                or result.message_ids != summary.message_ids
                or result.parent_summary_id != summary.parent_summary_id
            ):
                raise ValueError("Summary publication conflict")
            return result

    @staticmethod
    def _revision(identity, row):
        from app.context.models import ContextRevision

        if row is None:
            return None
        return ContextRevision(
            identity=identity,
            revision=row[0],
            base_revision=row[1],
            source_checkpoint_id=row[2],
            message_ids=tuple(row[3]),
            content_hash=row[4],
            archive_refs=tuple(row[5]),
            summary_id=row[6],
            policy_version=row[7],
            model_version=row[8],
            prompt_version=row[9],
            status=row[10],
            applied_checkpoint_id=row[11],
        )

    async def get_revision(self, identity, revision):
        async with self.pool.connection() as conn:
            row = await (
                await conn.execute(
                    "SELECT revision,base_revision,source_checkpoint_id,message_ids,content_hash,"
                    "archive_refs,summary_id,policy_version,model_version,prompt_version,status,"
                    "applied_checkpoint_id FROM context_revision WHERE user_id=%s "
                    "AND conversation_id=%s AND revision=%s",
                    (identity.user_id, identity.conversation_id, revision),
                )
            ).fetchone()
        return self._revision(identity, row)

    async def candidate_revision(self, identity, base_revision):
        async with self.pool.connection() as conn:
            row = await (
                await conn.execute(
                    "SELECT revision,base_revision,source_checkpoint_id,message_ids,content_hash,"
                    "archive_refs,summary_id,policy_version,model_version,prompt_version,status,"
                    "applied_checkpoint_id FROM context_revision WHERE user_id=%s "
                    "AND conversation_id=%s AND base_revision IS NOT DISTINCT FROM %s "
                    "AND status='PUBLISHED' ORDER BY revision LIMIT 1",
                    (identity.user_id, identity.conversation_id, base_revision),
                )
            ).fetchone()
        return self._revision(identity, row)

    @staticmethod
    async def _validate_base_coverage(conn, identity, base_revision, archive_refs, message_ids):
        """A replacement summary retains the complete coverage of its bound base."""
        first_summary = None
        visited = set()
        while base_revision is not None:
            if base_revision in visited:
                raise ValueError("Revision base cycle")
            visited.add(base_revision)
            row = await (
                await conn.execute(
                    "SELECT r.summary_id,r.status,s.archive_refs,s.message_ids,"
                    "r.base_revision,r.message_ids FROM context_revision r JOIN context_summary s "
                    "ON s.user_id=r.user_id AND s.conversation_id=r.conversation_id "
                    "AND s.summary_id=r.summary_id WHERE r.user_id=%s "
                    "AND r.conversation_id=%s AND r.revision=%s FOR SHARE OF r,s",
                    (identity.user_id, identity.conversation_id, base_revision),
                )
            ).fetchone()
            if (
                row is None
                or row[1] not in {"PUBLISHED", "APPLIED"}
                or tuple(archive_refs[: len(row[2])]) != tuple(row[2])
                or tuple(message_ids[: len(row[3])]) != tuple(row[3])
                or not row[5]
                or tuple(row[3][-len(row[5]) :]) != tuple(row[5])
                or (row[4] is not None and row[4] >= base_revision)
            ):
                raise ValueError("Revision does not cover base history")
            if first_summary is None:
                first_summary = row[0]
            base_revision = row[4]
        return first_summary

    async def validate_revision_base(self, identity, base_revision, summary_id):
        """Recheck persisted associations before handing a candidate to Graph."""
        async with self.pool.connection() as conn, conn.transaction():
            row = await (
                await conn.execute(
                    "SELECT archive_refs,message_ids FROM context_summary WHERE user_id=%s "
                    "AND conversation_id=%s AND summary_id=%s FOR SHARE",
                    (identity.user_id, identity.conversation_id, summary_id),
                )
            ).fetchone()
            if row is None:
                raise ValueError("Revision summary unavailable")
            return await self._validate_base_coverage(conn, identity, base_revision, *row)

    async def publish_revision(self, revision, *, archive_hashes):
        """Validate immutable source associations in one transaction before publication."""
        identity = revision.identity
        if (
            revision.status != "PREPARING"
            or not revision.message_ids
            or not revision.archive_refs
            or not revision.source_checkpoint_id
            or not revision.content_hash
            or revision.revision <= 0
            or (revision.base_revision is not None and revision.base_revision >= revision.revision)
            or len(set(revision.archive_refs)) != len(revision.archive_refs)
        ):
            raise ValueError("Invalid revision")
        async with self.pool.connection() as conn, conn.transaction():
            summary = await (
                await conn.execute(
                    "SELECT version,archive_refs,message_ids,source_checkpoint_id,policy_version,"
                    "model_version,prompt_version FROM context_summary WHERE user_id=%s "
                    "AND conversation_id=%s AND summary_id=%s FOR SHARE",
                    (identity.user_id, identity.conversation_id, revision.summary_id),
                )
            ).fetchone()
            if (
                summary is None
                or summary[0] != revision.revision
                or summary[1] != list(revision.archive_refs)
                or tuple(summary[2][-len(revision.message_ids) :]) != revision.message_ids
                or summary[3:]
                != (
                    revision.source_checkpoint_id,
                    revision.policy_version,
                    revision.model_version,
                    revision.prompt_version,
                )
            ):
                raise ValueError("Revision summary association mismatch")
            await self._validate_base_coverage(
                conn, identity, revision.base_revision, summary[1], summary[2]
            )
            ids = []
            for ref, expected_hash in zip(revision.archive_refs, archive_hashes, strict=True):
                row = await (
                    await conn.execute(
                        "SELECT message_ids,content_hash FROM context_archive WHERE user_id=%s "
                        "AND conversation_id=%s "
                        "AND archive_ref=%s AND status='READY' FOR SHARE",
                        (identity.user_id, identity.conversation_id, ref),
                    )
                ).fetchone()
                if row is None or row[1] != expected_hash:
                    raise ValueError("Revision archive unavailable or changed")
                ids.extend(row[0])
            if tuple(ids) != tuple(summary[2]) or len(set(ids)) != len(ids):
                raise ValueError("Revision coverage mismatch")
            await conn.execute(
                "INSERT INTO context_revision(user_id,conversation_id,revision,base_revision,"
                "source_checkpoint_id,message_ids,content_hash,archive_refs,summary_id,policy_version,"
                "model_version,prompt_version,status) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,"
                "'PREPARING') ON CONFLICT DO NOTHING",
                (
                    identity.user_id,
                    identity.conversation_id,
                    revision.revision,
                    revision.base_revision,
                    revision.source_checkpoint_id,
                    list(revision.message_ids),
                    revision.content_hash,
                    list(revision.archive_refs),
                    revision.summary_id,
                    revision.policy_version,
                    revision.model_version,
                    revision.prompt_version,
                ),
            )
            row = await (
                await conn.execute(
                    "SELECT revision,base_revision,source_checkpoint_id,message_ids,content_hash,"
                    "archive_refs,summary_id,policy_version,model_version,prompt_version,status,"
                    "applied_checkpoint_id FROM context_revision WHERE user_id=%s "
                    "AND conversation_id=%s "
                    "AND revision=%s FOR UPDATE",
                    (identity.user_id, identity.conversation_id, revision.revision),
                )
            ).fetchone()
            current = self._revision(identity, row)
            if (
                current.model_copy(update={"status": "PREPARING", "applied_checkpoint_id": None})
                != revision
            ):
                raise ValueError("Revision conflict")
            if current.status == "PREPARING":
                await conn.execute(
                    "UPDATE context_revision SET status='PUBLISHED' WHERE user_id=%s "
                    "AND conversation_id=%s AND revision=%s",
                    (identity.user_id, identity.conversation_id, revision.revision),
                )
                return current.model_copy(update={"status": "PUBLISHED"})
            return current

    async def mark_revision(self, identity, revision, status, checkpoint_id=None):
        if status not in {"STALE", "APPLIED"} or (status == "APPLIED") != bool(checkpoint_id):
            raise ValueError("Invalid revision receipt")
        async with self.pool.connection() as conn, conn.transaction():
            row = await (
                await conn.execute(
                    "UPDATE context_revision SET status=%s,applied_checkpoint_id=%s "
                    "WHERE user_id=%s "
                    "AND conversation_id=%s AND revision=%s "
                    "AND status='PUBLISHED' RETURNING revision",
                    (status, checkpoint_id, identity.user_id, identity.conversation_id, revision),
                )
            ).fetchone()
            if row is None:
                row = await (
                    await conn.execute(
                        "SELECT status,applied_checkpoint_id FROM context_revision "
                        "WHERE user_id=%s "
                        "AND conversation_id=%s AND revision=%s FOR UPDATE",
                        (identity.user_id, identity.conversation_id, revision),
                    )
                ).fetchone()
                if row is None or row[0] != status:
                    raise ValueError("Revision receipt conflict")
