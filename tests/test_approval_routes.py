"""Approval control plane exists only for local development/test."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


class ApprovalStub:
    def __init__(self):
        self.id = uuid4()
        self.actors = []
        self.row = {
            "approval_id": self.id,
            "subject_digest": "digest",
            "decision": "PENDING",
            "expires_at": datetime.now(UTC) + timedelta(minutes=30),
            "db_now": datetime.now(UTC),
            "interrupt_id": "i",
            "checkpoint_ns": "ns",
            "checkpoint_id": "cp",
        }

    async def list(self, *, decision=None):
        return [self.row]

    async def get(self, approval_id):
        return self.row if approval_id == str(self.id) else None

    async def decide(self, approval_id, *, actor, decision, expected_subject_digest):
        self.actors.append(actor.approver_id)
        self.row["decision"] = decision
        return self.row


def test_local_control_plane_and_production_boundary():
    app = create_app(Settings(_env_file=None, app_env="test"))
    with TestClient(app, client=("127.0.0.1", 1234)) as client:
        service = ApprovalStub()
        app.state.approval_service = service
        result = client.get("/admin/approvals")
        assert result.status_code == 200
        assert set(result.json()[0]) == {
            "approval_id",
            "subject_digest",
            "decision",
            "expires_at",
            "binding_status",
            "approval_validity",
            "can_decide",
            "can_resume",
        }
        assert result.json()[0]["can_decide"] is True and result.json()[0]["can_resume"] is False
        path = f"/admin/approvals/{service.id}/decision"
        assert (
            client.post(
                path,
                json={"decision": "APPROVED", "subject_digest": "digest", "approver_id": "client"},
            ).status_code
            == 422
        )
        assert (
            client.post(path, json={"decision": "APPROVED", "subject_digest": "digest"}).status_code
            == 200
        )
        assert service.actors == ["local-demo-approval"]

        class RepairRuntime:
            async def repair_approval_binding(self, reference, *, actor):
                assert reference.approval_id == str(service.id)
                assert actor.approver_id == "local-demo-approval"
                return {
                    "approval_id": reference.approval_id,
                    "binding_status": "bound",
                    "repaired": True,
                }

        app.state.agent_runtime = RepairRuntime()
        repair = f"/admin/approvals/{service.id}/repair-binding"
        assert client.post(repair, json={"interrupt_id": "client"}).status_code == 422
        assert client.post(repair, json={}).json()["repaired"] is True
    with TestClient(app, client=("192.0.2.10", 1234)) as client:
        assert client.get("/admin/approvals").status_code == 404
    prod = create_app(Settings(_env_file=None, app_env="production"))
    with TestClient(prod) as client:
        assert client.get("/admin/approvals").status_code == 404
        assert not hasattr(prod.state, "approval_actor_provider")
