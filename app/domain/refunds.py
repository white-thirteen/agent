"""Transactional simulated refunds. All external effects are local database facts."""

import hashlib
import json
from dataclasses import dataclass
from uuid import UUID

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb


class RefundRejected(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def canonical_digest(value: dict) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class RefundBusinessContext:
    user_id: str
    task_id: str
    run_id: str
    conversation_id: str
    thread_id: str
    workflow_id: str
    operation_id: str
    application_id: str
    approval_id: str | None
    expected_call_digest: str


@dataclass(frozen=True, slots=True)
class OriginalRefundCall:
    call_id: str
    tool_name: str
    tool_version: str
    raw_args: dict
    canonical_args: dict

    def call_digest(self):
        return canonical_digest(
            {
                "call_id": self.call_id,
                "name": self.tool_name,
                "version": self.tool_version,
                "args": self.canonical_args,
            }
        )


def application_subject(row):
    """Canonical immutable approval subject derived from a stored application."""
    return {
        "application_id": str(row["application_id"]),
        "operation_id": str(row["operation_id"]),
        "user_id": row["user_id"],
        "conversation_id": row["conversation_id"],
        "thread_id": str(row["thread_id"]),
        "task_id": row["task_id"],
        "workflow_id": row["workflow_id"],
        "call_id": row["call_id"],
        "tool_name": row["tool_name"],
        "tool_version": row["tool_version"],
        "canonical_args": row["canonical_args"],
        "args_digest": row["args_digest"],
        "amount": f"{row['amount']:.2f}",
        "currency": row["currency"],
    }


def _check_context(row, context, order_id):
    if (
        row["application_id"] != UUID(context.application_id)
        or row["operation_id"] != UUID(context.operation_id)
        or row["user_id"] != context.user_id
        or row["conversation_id"] != context.conversation_id
        or row["thread_id"] != UUID(context.thread_id)
        or row["task_id"] != context.task_id
        or row["workflow_id"] != context.workflow_id
        or context.task_id != context.workflow_id
        or row["order_id"] != order_id
        or row["tool_name"] != "refund_order"
        or row["canonical_args"] != {"order_id": order_id}
        or row["args_digest"] != canonical_digest(row["canonical_args"])
    ):
        raise RefundRejected("refund_context_mismatch")
    call = OriginalRefundCall(
        row["call_id"],
        row["tool_name"],
        row["tool_version"],
        row["raw_args"],
        row["canonical_args"],
    )
    if call.call_digest() != context.expected_call_digest:
        raise RefundRejected("refund_context_mismatch")


def _application_view(row):
    return {
        "application_id": str(row["application_id"]),
        "operation_id": str(row["operation_id"]),
        "order_id": row["order_id"],
        "amount": f"{row['amount']:.2f}",
        "currency": row["currency"],
        "status": row["status"],
    }


def _success_result(row):
    expected = {
        "operation_id": str(row["operation_id"]),
        "order_id": row["order_id"],
        "amount": f"{row['amount']:.2f}",
        "currency": row["currency"],
        "simulated": True,
    }
    if row["execution_result"] != expected:
        raise RefundRejected("refund_result_mismatch")
    return expected


class MockRefundService:
    def __init__(self, pool):
        self._pool = pool

    async def get_application_status(self, *, user_id, conversation_id, application_id):
        """Read only an owner's application and its associated approval and result."""
        async with self._pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    "SELECT r.*, a.approval_id, a.decision FROM refund_requests r "
                    "LEFT JOIN approvals a ON a.application_id=r.application_id "
                    "WHERE r.application_id=%s AND r.user_id=%s AND r.conversation_id=%s",
                    (UUID(application_id), user_id, conversation_id),
                )
                row = await cur.fetchone()
                if not row:
                    return None
                return _application_view(row) | {
                    "approval_id": str(row["approval_id"]) if row["approval_id"] else None,
                    "approval_decision": row["decision"],
                    "simulated": True,
                    "execution_result": _success_result(row)
                    if row["status"] == "SUCCEEDED"
                    else None,
                    "task_id": row["task_id"],
                    "thread_id": str(row["thread_id"]),
                }

    async def check_eligibility(self, *, context, order_id):
        async with self._pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                if isinstance(context, RefundBusinessContext):
                    await cur.execute(
                        "SELECT * FROM refund_requests WHERE operation_id=%s AND user_id=%s",
                        (UUID(context.operation_id), context.user_id),
                    )
                    previous = await cur.fetchone()
                    if previous and previous["status"] == "SUCCEEDED":
                        _check_context(previous, context, order_id)
                        if not context.approval_id:
                            raise RefundRejected("approval_not_valid")
                        await cur.execute(
                            "SELECT subject_snapshot,subject_digest FROM approvals "
                            "WHERE approval_id=%s AND application_id=%s",
                            (UUID(context.approval_id), previous["application_id"]),
                        )
                        approval = await cur.fetchone()
                        subject = application_subject(previous)
                        if (
                            not approval
                            or approval["subject_snapshot"] != subject
                            or approval["subject_digest"] != canonical_digest(subject)
                        ):
                            raise RefundRejected("approval_not_valid")
                        return {
                            "status": "SUCCEEDED",
                            "execution_result": _success_result(previous),
                        }
                await cur.execute(
                    "SELECT amount,currency,payment_status,is_refunded FROM demo_orders "
                    "WHERE order_id=%s AND owner_id=%s",
                    (order_id, context.user_id),
                )
                row = await cur.fetchone()
                if not row:
                    raise RefundRejected("order_not_accessible")
                if row["payment_status"] != "paid" or row["is_refunded"]:
                    raise RefundRejected("refund_not_eligible")
                return {
                    "order_id": order_id,
                    "amount": f"{row['amount']:.2f}",
                    "currency": row["currency"],
                    "simulated": True,
                }

    async def prepare_application(
        self, *, context: RefundBusinessContext, original_call: OriginalRefundCall
    ):
        if (
            context.task_id != context.workflow_id
            or original_call.call_digest() != context.expected_call_digest
        ):
            raise RefundRejected("refund_context_mismatch")
        if original_call.tool_name != "refund_order" or set(original_call.canonical_args) != {
            "order_id"
        }:
            raise RefundRejected("refund_call_mismatch")
        order_id = original_call.canonical_args["order_id"]
        async with self._pool.connection() as conn:
            async with conn.transaction():
                async with conn.cursor(row_factory=dict_row) as cur:
                    await cur.execute(
                        "SELECT amount,currency,payment_status,is_refunded FROM demo_orders "
                        "WHERE order_id=%s AND owner_id=%s FOR UPDATE",
                        (order_id, context.user_id),
                    )
                    order = await cur.fetchone()
                    if not order:
                        raise RefundRejected("order_not_accessible")
                    await cur.execute(
                        "SELECT thread_id FROM sessions WHERE user_id=%s AND conversation_id=%s",
                        (context.user_id, context.conversation_id),
                    )
                    session = await cur.fetchone()
                    if not session or session["thread_id"] != UUID(context.thread_id):
                        raise RefundRejected("refund_context_mismatch")
                    await cur.execute(
                        "SELECT * FROM refund_requests WHERE application_id=%s FOR UPDATE",
                        (UUID(context.application_id),),
                    )
                    row = await cur.fetchone()
                    if row:
                        _check_context(row, context, order_id)
                        if (
                            row["raw_args"] != original_call.raw_args
                            or row["canonical_args"] != original_call.canonical_args
                        ):
                            raise RefundRejected("refund_application_conflict")
                        return _application_view(row)
                    if order["payment_status"] != "paid" or order["is_refunded"]:
                        raise RefundRejected("refund_not_eligible")
                    await cur.execute(
                        "INSERT INTO refund_requests (application_id,operation_id,user_id,"
                        "conversation_id,thread_id,task_id,workflow_id,order_id,call_id,tool_name,tool_version,"
                        "raw_args,canonical_args,args_digest,amount,currency) VALUES "
                        "(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                        "ON CONFLICT DO NOTHING RETURNING *",
                        (
                            UUID(context.application_id),
                            UUID(context.operation_id),
                            context.user_id,
                            context.conversation_id,
                            UUID(context.thread_id),
                            context.task_id,
                            context.workflow_id,
                            order_id,
                            original_call.call_id,
                            original_call.tool_name,
                            original_call.tool_version,
                            Jsonb(original_call.raw_args),
                            Jsonb(original_call.canonical_args),
                            canonical_digest(original_call.canonical_args),
                            order["amount"],
                            order["currency"],
                        ),
                    )
                    row = await cur.fetchone()
                    if not row:
                        raise RefundRejected("refund_application_conflict")
                    return _application_view(row)

    async def get_operation(self, *, user_id, operation_id):
        async with self._pool.connection() as conn:
            async with conn.transaction():
                async with conn.cursor(row_factory=dict_row) as cur:
                    await cur.execute(
                        "SELECT order_id FROM refund_requests WHERE user_id=%s AND operation_id=%s",
                        (user_id, UUID(operation_id)),
                    )
                    target = await cur.fetchone()
                    if not target:
                        return None
                    # Wait behind an in-flight order update before deciding whether it committed.
                    await cur.execute(
                        "SELECT order_id FROM demo_orders "
                        "WHERE owner_id=%s AND order_id=%s FOR UPDATE",
                        (user_id, target["order_id"]),
                    )
                    if not await cur.fetchone():
                        raise RefundRejected("order_not_accessible")
                    await cur.execute(
                        "SELECT * FROM refund_requests "
                        "WHERE user_id=%s AND operation_id=%s FOR UPDATE",
                        (user_id, UUID(operation_id)),
                    )
                    row = await cur.fetchone()
                    if not row:
                        raise RefundRejected("refund_context_mismatch")
                    return _application_view(row) | {
                        "execution_result": _success_result(row)
                        if row["status"] == "SUCCEEDED"
                        else None
                    }

    async def execute_original(self, *, context: RefundBusinessContext, order_id: str):
        async with self._pool.connection() as conn:
            async with conn.transaction():
                async with conn.cursor(row_factory=dict_row) as cur:
                    await cur.execute(
                        "SELECT amount,currency,payment_status,is_refunded FROM demo_orders "
                        "WHERE order_id=%s AND owner_id=%s FOR UPDATE",
                        (order_id, context.user_id),
                    )
                    order = await cur.fetchone()
                    if not order:
                        raise RefundRejected("order_not_accessible")
                    await cur.execute(
                        "SELECT * FROM refund_requests WHERE application_id=%s FOR UPDATE",
                        (UUID(context.application_id),),
                    )
                    row = await cur.fetchone()
                    if not row:
                        raise RefundRejected("refund_context_mismatch")
                    _check_context(row, context, order_id)
                    await cur.execute(
                        "SELECT thread_id FROM sessions WHERE user_id=%s AND conversation_id=%s",
                        (context.user_id, context.conversation_id),
                    )
                    session = await cur.fetchone()
                    if not session or session["thread_id"] != row["thread_id"]:
                        raise RefundRejected("refund_context_mismatch")
                    if not context.approval_id:
                        raise RefundRejected("approval_not_valid")
                    await cur.execute(
                        "SELECT * FROM approvals "
                        "WHERE approval_id=%s AND application_id=%s FOR UPDATE",
                        (UUID(context.approval_id), row["application_id"]),
                    )
                    approval = await cur.fetchone()
                    if approval:
                        await cur.execute("SELECT clock_timestamp() AS db_now")
                        approval["db_now"] = (await cur.fetchone())["db_now"]
                    subject = application_subject(row)
                    if (
                        not approval
                        or approval["subject_snapshot"] != subject
                        or approval["subject_digest"] != canonical_digest(subject)
                        or not approval["interrupt_id"]
                        or not approval["checkpoint_ns"]
                        or not approval["checkpoint_id"]
                    ):
                        raise RefundRejected("approval_not_valid")
                    # A committed result remains true after the original approval expires.
                    if row["status"] == "SUCCEEDED":
                        return _success_result(row)
                    if (
                        approval["decision"] != "APPROVED"
                        or approval["expires_at"] <= approval["db_now"]
                    ):
                        raise RefundRejected("approval_not_valid")
                    if (
                        row["status"] != "PENDING"
                        or order["payment_status"] != "paid"
                        or order["is_refunded"]
                        or order["amount"] != row["amount"]
                        or order["currency"] != row["currency"]
                    ):
                        raise RefundRejected("refund_not_eligible")
                    result = {
                        "operation_id": str(row["operation_id"]),
                        "order_id": order_id,
                        "amount": f"{row['amount']:.2f}",
                        "currency": row["currency"],
                        "simulated": True,
                    }
                    await cur.execute(
                        "UPDATE demo_orders SET is_refunded=true WHERE order_id=%s AND owner_id=%s",
                        (order_id, context.user_id),
                    )
                    await cur.execute(
                        "UPDATE refund_requests SET status='SUCCEEDED', execution_result=%s, "
                        "executed_at=clock_timestamp() WHERE application_id=%s",
                        (Jsonb(result), row["application_id"]),
                    )
                    return result

    async def reject_application(self, *, context: RefundBusinessContext, reason_code: str):
        async with self._pool.connection() as conn:
            async with conn.transaction():
                async with conn.cursor(row_factory=dict_row) as cur:
                    await cur.execute(
                        "SELECT order_id FROM refund_requests "
                        "WHERE application_id=%s AND user_id=%s",
                        (UUID(context.application_id), context.user_id),
                    )
                    target = await cur.fetchone()
                    if not target:
                        raise RefundRejected("refund_context_mismatch")
                    await cur.execute(
                        "SELECT order_id FROM demo_orders "
                        "WHERE order_id=%s AND owner_id=%s FOR UPDATE",
                        (target["order_id"], context.user_id),
                    )
                    if not await cur.fetchone():
                        raise RefundRejected("order_not_accessible")
                    await cur.execute(
                        "SELECT * FROM refund_requests WHERE application_id=%s FOR UPDATE",
                        (UUID(context.application_id),),
                    )
                    row = await cur.fetchone()
                    _check_context(row, context, target["order_id"])
                    if context.approval_id:
                        await cur.execute(
                            "SELECT approval_id FROM approvals "
                            "WHERE approval_id=%s AND application_id=%s FOR UPDATE",
                            (UUID(context.approval_id), row["application_id"]),
                        )
                        if not await cur.fetchone():
                            raise RefundRejected("refund_context_mismatch")
                    if row["status"] == "SUCCEEDED":
                        raise RefundRejected("refund_already_succeeded")
                    if row["status"] == "PENDING":
                        await cur.execute(
                            "UPDATE refund_requests SET status='REJECTED', rejection_code=%s "
                            "WHERE application_id=%s RETURNING *",
                            (reason_code, row["application_id"]),
                        )
                        row = await cur.fetchone()
                    elif row["rejection_code"] != reason_code:
                        raise RefundRejected("refund_application_conflict")
                    return _application_view(row)
