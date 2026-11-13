"""Local demo approval persistence and auditing; this is not authentication."""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from app.domain.refunds import application_subject, canonical_digest


@dataclass(frozen=True, slots=True)
class ApprovalActor:
    approver_id: str


class ApprovalActorProvider(Protocol):
    def get_actor(self) -> ApprovalActor: ...


class LocalDemoApprovalActor:
    def get_actor(self) -> ApprovalActor:
        return ApprovalActor("local-demo-approval")


@dataclass(frozen=True, slots=True)
class InterruptBinding:
    interrupt_id: str
    checkpoint_ns: str
    checkpoint_id: str


@dataclass(frozen=True, slots=True)
class InterruptBindingRequest(InterruptBinding):
    # Expected facts travel with the runtime-verified binding into the locked CAS.
    # Keep them out of the persisted tool approval-binding snapshot contract.
    expected_subject_digest: str
    expected_decision: str


@dataclass(frozen=True, slots=True)
class ApprovalReference:
    approval_id: str


@dataclass(frozen=True, slots=True)
class VerifiedApproval:
    approval_id: str
    application_id: str
    operation_id: str
    subject_digest: str
    subject: dict
    approver_id: str
    decided_at: datetime
    expires_at: datetime


class ApprovalError(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


class ApprovalService:
    def __init__(self, pool):
        self._pool = pool

    async def register_pending(self, *, approval_id, subject):
        async with self._pool.connection() as conn:
            async with conn.transaction():
                async with conn.cursor(row_factory=dict_row) as cur:
                    await cur.execute(
                        "SELECT order_id,user_id FROM refund_requests WHERE application_id=%s",
                        (UUID(subject["application_id"]),),
                    )
                    target = await cur.fetchone()
                    if not target:
                        raise ApprovalError("approval_subject_mismatch")
                    await cur.execute(
                        "SELECT order_id FROM demo_orders "
                        "WHERE order_id=%s AND owner_id=%s FOR UPDATE",
                        (target["order_id"], target["user_id"]),
                    )
                    if not await cur.fetchone():
                        raise ApprovalError("approval_subject_mismatch")
                    await cur.execute(
                        "SELECT * FROM refund_requests WHERE application_id=%s FOR UPDATE",
                        (UUID(subject["application_id"]),),
                    )
                    app = await cur.fetchone()
                    if app:
                        await cur.execute(
                            "SELECT thread_id FROM sessions "
                            "WHERE user_id=%s AND conversation_id=%s",
                            (app["user_id"], app["conversation_id"]),
                        )
                        session = await cur.fetchone()
                    else:
                        session = None
                    if (
                        not app
                        or not session
                        or session["thread_id"] != app["thread_id"]
                        or application_subject(app) != subject
                        or app["task_id"] != app["workflow_id"]
                        or app["args_digest"] != canonical_digest(app["canonical_args"])
                    ):
                        raise ApprovalError("approval_subject_mismatch")
                    digest = canonical_digest(subject)
                    await cur.execute(
                        "SELECT * FROM approvals WHERE application_id=%s FOR UPDATE",
                        (app["application_id"],),
                    )
                    existing = await cur.fetchone()
                    if not existing and app["status"] != "PENDING":
                        raise ApprovalError("approval_subject_mismatch")
                    if existing:
                        if (
                            str(existing["approval_id"]) != approval_id
                            or existing["subject_snapshot"] != subject
                            or existing["subject_digest"] != digest
                        ):
                            raise ApprovalError("approval_subject_mismatch")
                        return existing
                    await cur.execute(
                        "INSERT INTO approvals "
                        "(approval_id,application_id,subject_snapshot,subject_digest) "
                        "VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING RETURNING *",
                        (UUID(approval_id), app["application_id"], Jsonb(subject), digest),
                    )
                    row = await cur.fetchone()
                    if not row:
                        await cur.execute(
                            "SELECT * FROM approvals WHERE application_id=%s FOR UPDATE",
                            (app["application_id"],),
                        )
                        row = await cur.fetchone()
                    if (
                        not row
                        or str(row["approval_id"]) != approval_id
                        or row["subject_snapshot"] != subject
                        or row["subject_digest"] != digest
                    ):
                        raise ApprovalError("approval_subject_mismatch")
                    return row

    async def bind_interrupt(self, approval_id, binding: InterruptBindingRequest):
        if not all((binding.interrupt_id, binding.checkpoint_ns, binding.checkpoint_id)):
            raise ApprovalError("approval_binding_invalid")
        async with self._pool.connection() as conn:
            async with conn.transaction():
                async with conn.cursor(row_factory=dict_row) as cur:
                    await cur.execute(
                        "SELECT * FROM approvals WHERE approval_id=%s FOR UPDATE",
                        (UUID(approval_id),),
                    )
                    row = await cur.fetchone()
                    if not row:
                        raise ApprovalError("approval_not_found")
                    await self._check_subject(cur, row)
                    if (
                        row["subject_digest"] != binding.expected_subject_digest
                        or row["decision"] != binding.expected_decision
                    ):
                        raise ApprovalError("approval_binding_conflict")
                    current = (row["interrupt_id"], row["checkpoint_ns"], row["checkpoint_id"])
                    expected = (binding.interrupt_id, binding.checkpoint_ns, binding.checkpoint_id)
                    if current == (None, None, None):
                        if row["decision"] != "PENDING":
                            raise ApprovalError("approval_binding_conflict")
                        await cur.execute(
                            "UPDATE approvals SET "
                            "interrupt_id=%s,checkpoint_ns=%s,checkpoint_id=%s "
                            "WHERE approval_id=%s RETURNING *",
                            (*expected, UUID(approval_id)),
                        )
                        return await cur.fetchone()
                    if current != expected:
                        raise ApprovalError("approval_binding_conflict")
                    return row

    async def decide(self, approval_id, *, actor: ApprovalActor, decision, expected_subject_digest):
        if decision not in ("APPROVED", "REJECTED"):
            raise ApprovalError("approval_decision_invalid")
        expired = False
        async with self._pool.connection() as conn:
            async with conn.transaction():
                async with conn.cursor(row_factory=dict_row) as cur:
                    await cur.execute(
                        "SELECT * FROM approvals WHERE approval_id=%s FOR UPDATE",
                        (UUID(approval_id),),
                    )
                    row = await cur.fetchone()
                    if not row:
                        raise ApprovalError("approval_not_found")
                    await cur.execute(
                        "SELECT r.*,s.thread_id AS session_thread FROM refund_requests r "
                        "JOIN sessions s ON s.user_id=r.user_id "
                        "AND s.conversation_id=r.conversation_id WHERE r.application_id=%s",
                        (row["application_id"],),
                    )
                    app = await cur.fetchone()
                    if (
                        not app
                        or app["session_thread"] != app["thread_id"]
                        or application_subject(app) != row["subject_snapshot"]
                        or canonical_digest(row["subject_snapshot"]) != row["subject_digest"]
                        or expected_subject_digest != row["subject_digest"]
                    ):
                        raise ApprovalError("approval_subject_mismatch")
                    if row["decision"] == decision:
                        return row
                    if row["decision"] != "PENDING":
                        raise ApprovalError("approval_decision_conflict")
                    if (
                        not row["interrupt_id"]
                        or not row["checkpoint_ns"]
                        or not row["checkpoint_id"]
                    ):
                        raise ApprovalError("approval_not_ready")
                    await cur.execute("SELECT clock_timestamp() AS db_now")
                    row["db_now"] = (await cur.fetchone())["db_now"]
                    if row["expires_at"] <= row["db_now"]:
                        await cur.execute(
                            "UPDATE approvals SET decision='EXPIRED',approver_id='system-expiry', "
                            "decided_at=clock_timestamp() WHERE approval_id=%s",
                            (UUID(approval_id),),
                        )
                        expired = True
                    else:
                        await cur.execute(
                            "UPDATE approvals SET decision=%s,approver_id=%s, "
                            "decided_at=clock_timestamp() WHERE approval_id=%s RETURNING *",
                            (decision, actor.approver_id, UUID(approval_id)),
                        )
                        row = await cur.fetchone()
        if expired:
            raise ApprovalError("approval_expired")
        return row

    async def get(self, approval_id):
        async with self._pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    "SELECT *,clock_timestamp() AS db_now FROM approvals WHERE approval_id=%s",
                    (UUID(approval_id),),
                )
                row = await cur.fetchone()
                if row:
                    await self._check_subject(cur, row)
                return row

    async def get_application(self, approval_id):
        """Read the matching application for internal checkpoint association checks."""
        approval = await self.get(approval_id)
        if not approval:
            raise ApprovalError("approval_not_found")
        async with self._pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    "SELECT * FROM refund_requests WHERE application_id=%s",
                    (approval["application_id"],),
                )
                application = await cur.fetchone()
                if (
                    not application
                    or application_subject(application) != approval["subject_snapshot"]
                ):
                    raise ApprovalError("approval_subject_mismatch")
                return approval, application

    async def prepare_resume(self, approval_id, *, interrupt_id, checkpoint_ns):
        """Recheck original binding and decision under lock immediately before admission."""
        async with self._pool.connection() as conn:
            async with conn.transaction():
                async with conn.cursor(row_factory=dict_row) as cur:
                    await cur.execute(
                        "SELECT * FROM approvals WHERE approval_id=%s FOR UPDATE",
                        (UUID(approval_id),),
                    )
                    row = await cur.fetchone()
                    if not row:
                        raise ApprovalError("approval_not_found")
                    await self._check_subject(cur, row)
                    if (
                        not row["checkpoint_id"]
                        or row["interrupt_id"] != interrupt_id
                        or row["checkpoint_ns"] != checkpoint_ns
                    ):
                        raise ApprovalError("approval_binding_conflict")
                    await cur.execute("SELECT clock_timestamp() AS db_now")
                    row["db_now"] = (await cur.fetchone())["db_now"]
                    if row["decision"] == "PENDING":
                        if row["expires_at"] > row["db_now"]:
                            raise ApprovalError("approval_pending")
                        await cur.execute(
                            "UPDATE approvals SET decision='EXPIRED',approver_id='system-expiry', "
                            "decided_at=clock_timestamp() WHERE approval_id=%s RETURNING *",
                            (UUID(approval_id),),
                        )
                        expired_row = await cur.fetchone()
                        expired_row["db_now"] = row["db_now"]
                        return expired_row
                    return row

    @staticmethod
    async def _check_subject(cur, row):
        await cur.execute(
            "SELECT r.*,s.thread_id AS session_thread FROM refund_requests r "
            "JOIN sessions s ON s.user_id=r.user_id AND s.conversation_id=r.conversation_id "
            "WHERE r.application_id=%s",
            (row["application_id"],),
        )
        app = await cur.fetchone()
        if (
            not app
            or app["session_thread"] != app["thread_id"]
            or app["task_id"] != app["workflow_id"]
            or app["args_digest"] != canonical_digest(app["canonical_args"])
            or application_subject(app) != row["subject_snapshot"]
            or canonical_digest(row["subject_snapshot"]) != row["subject_digest"]
        ):
            raise ApprovalError("approval_subject_mismatch")

    async def list(self, *, decision=None, limit=100):
        async with self._pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    "SELECT *,clock_timestamp() AS db_now FROM approvals "
                    "WHERE (%s::text IS NULL OR decision=%s) ORDER BY created_at DESC LIMIT %s",
                    (decision, decision, limit),
                )
                rows = await cur.fetchall()
                for row in rows:
                    await self._check_subject(cur, row)
                return rows

    async def verify_for_call(self, reference, *, original_call, context, interrupt_binding):
        row = await self.get(reference.approval_id)
        if not row:
            raise ApprovalError("approval_not_found")
        subject = row["subject_snapshot"]
        binding = (row["interrupt_id"], row["checkpoint_ns"], row["checkpoint_id"])
        if (
            row["decision"] != "APPROVED"
            or row["expires_at"] <= row["db_now"]
            or binding
            != (
                interrupt_binding.interrupt_id,
                interrupt_binding.checkpoint_ns,
                interrupt_binding.checkpoint_id,
            )
            or canonical_digest(subject) != row["subject_digest"]
            or subject.get("user_id") != context.user_id
            or subject.get("conversation_id") != context.conversation_id
            or subject.get("thread_id") != context.thread_id
            or subject.get("task_id") != context.task_id
            or subject.get("workflow_id") != context.workflow_id
            or subject.get("application_id") != context.application_id
            or subject.get("operation_id") != context.operation_id
            or subject.get("call_id") != original_call.call_id
            or subject.get("tool_name") != original_call.tool_name
            or subject.get("tool_version") != original_call.tool_version
            or subject.get("canonical_args") != original_call.canonical_args
            or original_call.call_digest() != context.expected_call_digest
        ):
            raise ApprovalError("approval_not_valid")
        async with self._pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    "SELECT r.*, s.thread_id AS session_thread FROM refund_requests r "
                    "JOIN sessions s ON s.user_id=r.user_id "
                    "AND s.conversation_id=r.conversation_id "
                    "JOIN approvals a ON a.application_id=r.application_id "
                    "WHERE r.application_id=%s AND a.approval_id=%s "
                    "AND a.decision='APPROVED' AND a.expires_at > clock_timestamp() "
                    "AND a.subject_digest=%s AND a.interrupt_id=%s "
                    "AND a.checkpoint_ns=%s AND a.checkpoint_id=%s",
                    (
                        UUID(context.application_id),
                        UUID(reference.approval_id),
                        row["subject_digest"],
                        *binding,
                    ),
                )
                app = await cur.fetchone()
                if (
                    not app
                    or application_subject(app) != subject
                    or app["session_thread"] != app["thread_id"]
                    or app["raw_args"] != original_call.raw_args
                    or app["args_digest"] != canonical_digest(original_call.canonical_args)
                ):
                    raise ApprovalError("approval_not_valid")
        return VerifiedApproval(
            str(row["approval_id"]),
            str(row["application_id"]),
            subject["operation_id"],
            row["subject_digest"],
            subject,
            row["approver_id"],
            row["decided_at"],
            row["expires_at"],
        )
