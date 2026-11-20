"""Bounded, session-exclusive task-after maintenance with durable work records."""

import asyncio
import logging
from uuid import NAMESPACE_URL, uuid5

import psycopg
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.messages.utils import count_tokens_approximately

from app.context.archive_store import canonical, digest, make_segment
from app.context.compaction import SUMMARY_PROMPT_VERSION
from app.context.manager import select_prefix
from app.context.models import ContextRevision, PublicInteraction, PublicMessage, SessionIdentity
from app.runtime.models import TaskStatus

logger = logging.getLogger(__name__)
POLICY = "context-v2-231"
BUDGET = "context-v2-231-advisory-v1"


def interactions(values):
    """Require trustworthy metadata; do not infer old task status from text."""
    groups = []
    metadata = values.get("public_message_metadata", {})
    for message in values.get("messages", []):
        item = metadata.get(message.id)
        if (
            not item
            or not item.get("task_id")
            or not message.id
            or type(message) not in (HumanMessage, AIMessage)
            or not isinstance(message.content, str)
            or isinstance(message, AIMessage)
            and (message.tool_calls or message.invalid_tool_calls)
        ):
            return ()
        task_id = item["task_id"]
        try:
            status = TaskStatus(item["task_status"]).name
        except (KeyError, ValueError):
            return ()
        if not groups or groups[-1][0] != task_id:
            groups.append((task_id, status, []))
        if groups[-1][1] != status:
            return ()
        groups[-1][2].append(
            PublicMessage(
                message_id=message.id,
                role="user" if type(message) is HumanMessage else "assistant",
                content=message.content,
                task_id=task_id,
                run_id=item.get("run_id"),
            )
        )
    return tuple(
        PublicInteraction(task_id=t, task_status=s, messages=tuple(m)) for t, s, m in groups
    )


class ContextMaintenance:
    def __init__(self, runtime, manager, graph, gateway, settings):
        self.runtime, self.manager, self.graph = runtime, manager, graph
        self.gateway, self.settings = gateway, settings
        self.tasks = set()
        self.stopping = False

    @property
    def enabled(self):
        return bool(
            self.gateway
            and self.settings.context_summary_output_tokens
            and self.settings.context_model_window_tokens
            and self.settings.context_model_output_tokens
        )

    async def _source(self, identity, snapshot, *, retain_recent=None):
        values = snapshot.values
        if (
            snapshot.next
            or snapshot.interrupts
            or values.get("user_id") != identity.user_id
            or values.get("conversation_id") != identity.conversation_id
            or values.get("task_status") not in (TaskStatus.COMPLETED, TaskStatus.REJECTED)
        ):
            return None
        parts = interactions(values)
        selected = select_prefix(
            parts,
            retain_recent=(
                self.settings.context_archive_retain_interactions
                if retain_recent is None
                else retain_recent
            ),
            max_messages=self.settings.context_archive_segment_messages,
        )
        if not selected:
            return None
        checkpoint = snapshot.config["configurable"]["checkpoint_id"]
        segment_id, segment_hash, _ = make_segment(identity, checkpoint, selected)
        archive_ref = identity.archive_ref(segment_id)
        base = values.get("context_ref")
        parent = None
        preceding = []
        refs = []
        if base:
            parent = await self.manager.repository.get_summary(identity, base["summary_id"])
            revision = await self.manager.repository.get_revision(identity, base["revision"])
            if parent is None or revision is None or revision.summary_id != parent.summary_id:
                raise ValueError("Base context unavailable")
            remaining = self.settings.context_archive_read_bytes
            for ref in parent.archive_refs:
                archive = await self.manager.repository.get(identity, ref)
                if archive is None:
                    raise ValueError("Base archive unavailable")
                data = self.manager.store.read(archive, remaining)
                remaining -= self.manager.store._path(archive.relative_path).stat().st_size
                if remaining < 0:
                    raise ValueError("Archive read limit exceeded")
                preceding.extend(data)
            refs.extend(parent.archive_refs)
        refs.append(archive_ref)
        all_messages = [*preceding, *selected]
        return {
            "parts": parts,
            "selected": selected,
            "checkpoint": checkpoint,
            "archive_ref": archive_ref,
            "segment_hash": segment_hash,
            "refs": tuple(refs),
            "ids": tuple(m.message_id for m in all_messages),
            "hash": digest(canonical([m.model_dump() for m in all_messages])),
            "base": base,
            "parent": parent,
        }

    async def register(self, record):
        if not self.enabled or self.stopping or record.execution.execution_mode != "normal":
            return None
        identity = SessionIdentity(
            user_id=record.context.user_id, conversation_id=record.context.conversation_id
        )
        snapshot = await self.graph.aget_state(
            {"configurable": {"thread_id": record.context.thread_id}}
        )
        if (
            snapshot.values.get("task_id") != record.execution.context.task_id
            or record.context.thread_id in self.runtime._uncertain
        ):
            return None
        source = await self._source(identity, snapshot)
        if source is None:
            return None
        work_id = str(
            uuid5(
                NAMESPACE_URL, canonical([identity.model_dump(), source["hash"], POLICY]).decode()
            )
        )
        work = await self.manager.repository.register_maintenance(
            identity,
            maintenance_id=work_id,
            source_task_id=record.execution.context.task_id,
            source_run_id=record.context.run_id,
            source_checkpoint_id=source["checkpoint"],
            message_ids=source["ids"],
            content_hash=source["hash"],
            policy_version=POLICY,
            budget_version=BUDGET,
            max_input_tokens=self.settings.context_archive_read_tokens,
            max_output_tokens=self.settings.context_summary_output_tokens,
            archive_refs=source["refs"],
        )
        return work["maintenance_id"], record.context.thread_id

    def schedule(self, work_id, thread_id):
        if self.stopping or len(self.tasks) >= self.settings.runtime_max_active_runs:
            return
        task = asyncio.create_task(self._run(work_id, thread_id), name="context-maintenance")
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    async def _repair_published_receipt(self, identity, work, prepared):
        """Link an already-published revision only after verifying its complete source."""
        if work["status"] != "SUCCEEDED" or not work["summary_id"]:
            return False
        base = prepared["base"]
        version = base["revision"] + 1 if base else 1
        revision = await self.manager.repository.get_revision(identity, version)
        if (
            revision is None
            or revision.status not in {"PUBLISHED", "APPLIED"}
            or revision.base_revision != (base["revision"] if base else None)
            or revision.source_checkpoint_id != work["source_checkpoint_id"]
            or revision.message_ids != tuple(m.message_id for m in prepared["selected"])
            or revision.content_hash != prepared["segment_hash"]
            or revision.archive_refs != prepared["refs"]
            or revision.summary_id != work["summary_id"]
            or revision.policy_version != work["policy_version"]
        ):
            return False
        parent = prepared["parent"]
        parent_id = parent.summary_id if parent else None
        ids, _, _, input_hash, scope_hash = await self.manager._summary_source(
            identity,
            archive_refs=revision.archive_refs,
            parent_summary_id=parent_id,
            source_checkpoint_id=revision.source_checkpoint_id,
            version=version,
            policy_version=revision.policy_version,
            model_version=revision.model_version,
            prompt_version=revision.prompt_version,
            max_bytes=self.settings.context_archive_read_bytes,
        )
        if ids != tuple(work["message_ids"]) or scope_hash != work["content_hash"]:
            return False
        summary = await self.manager.repository.find_summary(
            identity,
            input_hash=input_hash,
            version=version,
            source_checkpoint_id=revision.source_checkpoint_id,
            policy_version=revision.policy_version,
            model_version=revision.model_version,
            prompt_version=revision.prompt_version,
        )
        if (
            summary is None
            or summary.summary_id != work["summary_id"]
            or summary.archive_refs != revision.archive_refs
            or summary.message_ids != ids
            or summary.parent_summary_id != parent_id
        ):
            return False
        async with self.manager.repository.pool.connection() as conn:
            row = await (
                await conn.execute(
                    "UPDATE context_maintenance SET revision=%s "
                    "WHERE maintenance_id=%s AND user_id=%s AND conversation_id=%s "
                    "AND source_checkpoint_id=%s AND status='SUCCEEDED' AND summary_id=%s "
                    "AND revision IS NULL RETURNING revision",
                    (
                        version,
                        work["maintenance_id"],
                        identity.user_id,
                        identity.conversation_id,
                        work["source_checkpoint_id"],
                        work["summary_id"],
                    ),
                )
            ).fetchone()
        return row is not None

    async def resume_pending(self):
        if not self.enabled or self.stopping:
            return
        async with self.manager.repository.pool.connection() as conn:
            # Expired unclaimed work cannot spend new budget. A previously
            # committed Summary is still eligible for publication recovery.
            ready = (
                "EXISTS (SELECT 1 FROM context_summary x WHERE x.user_id=m.user_id "
                "AND x.conversation_id=m.conversation_id "
                "AND x.source_checkpoint_id=m.source_checkpoint_id "
                "AND x.policy_version=m.policy_version AND x.model_version=%s "
                "AND x.prompt_version=%s AND x.archive_refs=m.archive_refs "
                "AND x.message_ids=m.message_ids)"
            )
            await conn.execute(
                "UPDATE context_maintenance m SET status='EXHAUSTED' "
                "WHERE m.budget_version=%s AND m.status IN ('PENDING','FAILED','INTERRUPTED') "
                "AND (m.reserved_attempts>=2 OR m.deadline_at<=clock_timestamp()) AND NOT " + ready,
                (BUDGET, self.settings.model_name, SUMMARY_PROMPT_VERSION),
            )
            rows = await (
                await conn.execute(
                    "SELECT m.maintenance_id,s.thread_id FROM context_maintenance m "
                    "JOIN sessions s ON s.user_id=m.user_id "
                    "AND s.conversation_id=m.conversation_id "
                    "WHERE m.budget_version=%s AND m.revision IS NULL "
                    "AND m.status IN ('PENDING','RUNNING','FAILED','INTERRUPTED',"
                    "'SUCCEEDED','EXHAUSTED') "
                    "AND ((m.reserved_attempts<2 AND m.deadline_at>clock_timestamp()) "
                    "OR m.status='SUCCEEDED' OR m.status='RUNNING' OR "
                    + ready
                    + ") ORDER BY CASE WHEN m.status='RUNNING' AND "
                    "(m.reserved_attempts>=2 OR m.deadline_at<=clock_timestamp()) "
                    "THEN 1 ELSE 0 END, "
                    "m.deadline_at LIMIT %s",
                    (
                        BUDGET,
                        self.settings.model_name,
                        SUMMARY_PROMPT_VERSION,
                        self.settings.runtime_max_active_runs,
                    ),
                )
            ).fetchall()
        for work_id, thread_id in rows:
            self.schedule(work_id, str(thread_id))

    async def _run(self, work_id, thread_id):
        token = None
        # Only this integration's budget version uses this advisory lock. Its
        # release proves the former executor for that work is no longer alive.
        try:
            pool = self.manager.repository.pool
            async with await psycopg.AsyncConnection.connect(
                pool.conninfo, **{**(pool.kwargs or {}), "autocommit": True}
            ) as conn:
                row = await (
                    await conn.execute(
                        "SELECT pg_try_advisory_lock(hashtextextended(%s, 231))", (work_id,)
                    )
                ).fetchone()
                if not row[0]:
                    return
                try:
                    if self.stopping or thread_id in self.runtime._claims:
                        return
                    token = object()
                    self.runtime._claims[thread_id] = token
                    work = await self.manager.repository.maintenance(work_id)
                    if (
                        work is None
                        or work["budget_version"] != BUDGET
                        or work["policy_version"] != POLICY
                    ):
                        return
                    if work["revision"] is not None:
                        return
                    if work["status"] == "RUNNING":
                        await self.manager.repository.interrupt_maintenance(work_id)
                        work = await self.manager.repository.maintenance(work_id)
                    if work["status"] not in (
                        "PENDING",
                        "FAILED",
                        "INTERRUPTED",
                        "SUCCEEDED",
                        "EXHAUSTED",
                    ):
                        return
                    if self.stopping or thread_id in self.runtime._uncertain:
                        return
                    latest = await self.graph.aget_state({"configurable": {"thread_id": thread_id}})
                    if (
                        latest.next
                        or latest.interrupts
                        or latest.values.get("task_status")
                        not in (TaskStatus.COMPLETED, TaskStatus.REJECTED)
                    ):
                        return
                    source = await self.graph.aget_state(
                        {
                            "configurable": {
                                "thread_id": thread_id,
                                "checkpoint_id": work["source_checkpoint_id"],
                            }
                        }
                    )
                    identity = SessionIdentity(
                        user_id=work["user_id"], conversation_id=work["conversation_id"]
                    )
                    if (latest.values.get("user_id"), latest.values.get("conversation_id")) != (
                        identity.user_id,
                        identity.conversation_id,
                    ):
                        return
                    prepared = await self._source(identity, source)
                    if (
                        prepared is None
                        or prepared["checkpoint"] != work["source_checkpoint_id"]
                        or prepared["ids"] != tuple(work["message_ids"])
                        or prepared["hash"] != work["content_hash"]
                        or prepared["refs"] != tuple(work["archive_refs"])
                    ):
                        return
                    # The Graph may already have adopted this revision. Repairing
                    # this association does not publish, apply, or invoke a model.
                    if await self._repair_published_receipt(identity, work, prepared):
                        return
                    old_messages = source.values.get("messages", [])
                    if (
                        latest.values.get("messages", [])[: len(old_messages)] != old_messages
                        or latest.values.get("context_ref") != source.values.get("context_ref")
                        or any(
                            latest.values.get("public_message_metadata", {}).get(m.id)
                            != source.values.get("public_message_metadata", {}).get(m.id)
                            for m in old_messages
                        )
                    ):
                        return
                    archive = await self.manager.publish(
                        identity,
                        prepared["checkpoint"],
                        prepared["parts"],
                        retain_recent=self.settings.context_archive_retain_interactions,
                        max_messages=self.settings.context_archive_segment_messages,
                        session_status=TaskStatus(source.values["task_status"]).name,
                    )
                    if archive.archive_ref != prepared["archive_ref"]:
                        raise ValueError("Archive source changed")
                    if self.stopping:
                        return
                    base = prepared["base"]
                    version = base["revision"] + 1 if base else 1
                    parent = prepared["parent"]
                    summary, _ = await self.manager.compact(
                        identity,
                        archive_refs=prepared["refs"],
                        parent_summary_id=parent.summary_id if parent else None,
                        source_checkpoint_id=prepared["checkpoint"],
                        version=version,
                        policy_version=POLICY,
                        model_version=self.settings.model_name,
                        prompt_version=SUMMARY_PROMPT_VERSION,
                        max_bytes=self.settings.context_archive_read_bytes,
                        gateway=self.gateway,
                        token_counter=count_tokens_approximately,
                        max_input_tokens=work["max_input_tokens"],
                        max_output_tokens=work["max_output_tokens"],
                        settings=self.settings,
                        maintenance={
                            "maintenance_id": work_id,
                            "source_task_id": work["source_task_id"],
                            "source_run_id": work["source_run_id"],
                            "budget_version": BUDGET,
                        },
                    )
                    revision = ContextRevision(
                        identity=identity,
                        revision=version,
                        base_revision=base["revision"] if base else None,
                        source_checkpoint_id=prepared["checkpoint"],
                        message_ids=tuple(m.message_id for m in prepared["selected"]),
                        content_hash=prepared["segment_hash"],
                        archive_refs=prepared["refs"],
                        summary_id=summary.summary_id,
                        policy_version=POLICY,
                        model_version=self.settings.model_name,
                        prompt_version=SUMMARY_PROMPT_VERSION,
                        status="PREPARING",
                    )
                    published = await self.manager.publish_revision(
                        revision, max_bytes=self.settings.context_archive_read_bytes
                    )
                    if published.status not in {"PUBLISHED", "APPLIED"}:
                        return
                    async with self.manager.repository.pool.connection() as receipt:
                        await receipt.execute(
                            "UPDATE context_maintenance SET revision=%s "
                            "WHERE maintenance_id=%s AND status='SUCCEEDED' AND summary_id=%s",
                            (version, work_id, summary.summary_id),
                        )
                finally:
                    if token is not None:
                        self.runtime._release(thread_id, token)
                    await conn.execute(
                        "SELECT pg_advisory_unlock(hashtextextended(%s, 231))", (work_id,)
                    )
        except Exception as error:
            import traceback

            frame = traceback.extract_tb(error.__traceback__)[-1]
            logger.warning(
                "Context maintenance deferred category=%s location=%s:%s",
                type(error).__name__,
                frame.name,
                frame.lineno,
            )

    async def shutdown(self):
        self.stopping = True
        for task in tuple(self.tasks):
            task.cancel()
        if self.tasks:
            await asyncio.gather(*self.tasks, return_exceptions=True)
