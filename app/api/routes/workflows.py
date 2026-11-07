"""Workflow routes will be added when lifecycle management is implemented."""

from fastapi import APIRouter

router = APIRouter(prefix="/agent/workflows", tags=["workflows"])
