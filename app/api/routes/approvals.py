"""Development/test approval control plane with a server-owned audit actor."""

from datetime import datetime
from ipaddress import ip_address
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from psycopg import Error as DatabaseError
from psycopg_pool import PoolClosed, PoolTimeout
from pydantic import BaseModel, ConfigDict

from app.workflows.approvals import ApprovalError, ApprovalReference


def require_loopback(request: Request):
    try:
        local = request.client is not None and ip_address(request.client.host).is_loopback
    except ValueError:
        local = False
    if not local:
        raise HTTPException(status_code=404, detail={"code": "not_found"})


router = APIRouter(
    prefix="/admin/approvals",
    tags=["local-demo-approvals"],
    dependencies=[Depends(require_loopback)],
)


class DecisionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: Literal["APPROVED", "REJECTED"]
    subject_digest: str


class EmptyInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ApprovalView(BaseModel):
    approval_id: UUID
    subject_digest: str
    decision: Literal["PENDING", "APPROVED", "REJECTED", "EXPIRED"]
    expires_at: datetime
    binding_status: Literal["unbound", "bound"]
    approval_validity: Literal["valid", "pending", "expired", "rejected"]
    can_decide: bool
    can_resume: bool


async def _view(row, runtime):
    bound = all(row[key] is not None for key in ("interrupt_id", "checkpoint_ns", "checkpoint_id"))
    expired = row["expires_at"] <= row["db_now"]
    decision = row["decision"]
    validity = (
        "rejected"
        if decision == "REJECTED"
        else "expired"
        if expired or decision == "EXPIRED"
        else "valid"
        if decision == "APPROVED"
        else "pending"
    )
    return ApprovalView(
        approval_id=row["approval_id"],
        subject_digest=row["subject_digest"],
        decision=decision,
        expires_at=row["expires_at"],
        binding_status="bound" if bound else "unbound",
        approval_validity=validity,
        can_decide=decision == "PENDING" and bound and not expired,
        can_resume=await runtime.can_resume_approval(ApprovalReference(str(row["approval_id"]))),
    )


def _fail(error):
    status = 404 if error.code == "approval_not_found" else 409
    raise HTTPException(status_code=status, detail={"code": error.code}) from None


@router.get("")
async def list_approvals(
    request: Request, decision: Literal["PENDING", "APPROVED", "REJECTED", "EXPIRED"] | None = None
):
    service = request.app.state.approval_service
    if service is None:
        raise HTTPException(status_code=503, detail={"code": "approval_unavailable"})
    try:
        return [
            await _view(row, request.app.state.agent_runtime)
            for row in await service.list(decision=decision)
        ]
    except ApprovalError as error:
        _fail(error)
    except (DatabaseError, PoolClosed, PoolTimeout):
        raise HTTPException(status_code=503, detail={"code": "approval_unavailable"}) from None


@router.get("/{approval_id}")
async def approval_detail(approval_id: UUID, request: Request):
    service = request.app.state.approval_service
    if service is None:
        raise HTTPException(status_code=503, detail={"code": "approval_unavailable"})
    try:
        row = await service.get(str(approval_id))
    except ApprovalError as error:
        _fail(error)
    except (DatabaseError, PoolClosed, PoolTimeout):
        raise HTTPException(status_code=503, detail={"code": "approval_unavailable"}) from None
    if not row:
        raise HTTPException(status_code=404, detail={"code": "approval_not_found"})
    return await _view(row, request.app.state.agent_runtime)


@router.post("/{approval_id}/decision")
async def decision(approval_id: UUID, body: DecisionInput, request: Request):
    service = request.app.state.approval_service
    if service is None:
        raise HTTPException(status_code=503, detail={"code": "approval_unavailable"})
    try:
        await service.decide(
            str(approval_id),
            actor=request.app.state.approval_actor_provider.get_actor(),
            decision=body.decision,
            expected_subject_digest=body.subject_digest,
        )
        row = await service.get(str(approval_id))
    except ApprovalError as error:
        _fail(error)
    except (DatabaseError, PoolClosed, PoolTimeout):
        raise HTTPException(status_code=503, detail={"code": "approval_unavailable"}) from None
    return {"approval": await _view(row, request.app.state.agent_runtime), "resume_required": True}


@router.post("/{approval_id}/repair-binding")
async def repair_binding(approval_id: UUID, body: EmptyInput, request: Request):
    return await request.app.state.agent_runtime.repair_approval_binding(
        ApprovalReference(str(approval_id)),
        actor=request.app.state.approval_actor_provider.get_actor(),
    )


@router.post("/{approval_id}/resume")
async def resume(approval_id: UUID, request: Request, body: EmptyInput | None = None):
    result = await request.app.state.agent_runtime.resume_approval(
        ApprovalReference(str(approval_id)),
        actor=request.app.state.approval_actor_provider.get_actor(),
    )
    return JSONResponse(jsonable_encoder(result), status_code=202 if result.accepted else 200)
