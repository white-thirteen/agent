"""Real-PG regression for the immutable 004 and corrective 005 constraints."""

import json
import os
from uuid import uuid4

import psycopg
import pytest
from pydantic import SecretStr

from app.core.config import Settings
from app.infrastructure.postgres import connection_kwargs, validate_test_target
from scripts import run_async


def test_approval_subject_constraint_on_real_postgres():
    raw = os.environ.get("AGENT_TEST_DATABASE_URL")
    if not raw:
        pytest.skip("Explicit test database required")
    url = SecretStr(raw)
    validate_test_target(url, Settings().database_url)

    async def scenario():
        async with await psycopg.AsyncConnection.connect(**connection_kwargs(url)) as conn:
            assert await (
                await conn.execute("SELECT current_database(), current_user")
            ).fetchone() == ("agent_demo_test", "agent_test")
            uid = "approval-test-" + uuid4().hex
            thread, appid, operation, approval = uuid4(), uuid4(), uuid4(), uuid4()
            await conn.execute(
                "INSERT INTO sessions (user_id,conversation_id,thread_id) VALUES (%s,%s,%s)",
                (uid, "c", thread),
            )
            await conn.execute(
                "INSERT INTO demo_orders VALUES (%s,%s,1.00,'CNY','paid',false,now())", (uid, uid)
            )
            await conn.execute(
                "INSERT INTO refund_requests (application_id,operation_id,user_id,conversation_id,"
                "thread_id,task_id,workflow_id,order_id,call_id,tool_name,tool_version,raw_args,"
                "canonical_args,args_digest,amount,currency) "
                "VALUES (%s,%s,%s,'c',%s,'task','task',%s,'call','refund_order','1',"
                "'{}','{}','digest',1.00,'CNY')",
                (appid, operation, uid, thread, uid),
            )
            query = (
                "INSERT INTO approvals "
                "(approval_id,application_id,subject_snapshot,subject_digest) "
                "VALUES (%s,%s,%s::jsonb,'digest')"
            )
            for subject in [
                {},
                {"task_id": "x"},
                {"workflow_id": "x"},
                {"task_id": None, "workflow_id": None},
                {"task_id": 1, "workflow_id": 1},
                {"task_id": True, "workflow_id": True},
                {"task_id": [], "workflow_id": []},
                {"task_id": {}, "workflow_id": {}},
                {"task_id": "", "workflow_id": ""},
                {"task_id": "x", "workflow_id": "y"},
            ]:
                with pytest.raises(psycopg.errors.CheckViolation):
                    async with conn.transaction():
                        await conn.execute(query, (approval, appid, json.dumps(subject)))
            await conn.execute(
                query, (approval, appid, json.dumps({"task_id": "x", "workflow_id": "x"}))
            )
            await conn.rollback()

    run_async(scenario())
