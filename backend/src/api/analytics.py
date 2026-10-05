"""Phân tích: phễu tuyển sinh, giám sát công bằng, Rubric Lab."""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from src.api.deps import Principal, require
from src.schemas.responses.analytics import FairnessOut, FunnelOut, LabIntakeOut, LabOut
from src.services import analytics
from src.services.tenancy import OrgDb, org_db

router = APIRouter(prefix="/analytics", tags=["analytics"])


class LabIn(BaseModel):
    intake_ids: Annotated[list[uuid.UUID], Field(min_length=1, max_length=10)]
    weights: dict[str, float] | None = None


@router.get("/funnel", response_model=FunnelOut)
async def funnel(
    intake_id: uuid.UUID, _: Principal = Depends(require("analytics.read")), db: OrgDb = Depends(org_db)
) -> dict[str, Any]:
    return await analytics.funnel(db, intake_id)


@router.get("/fairness", response_model=FairnessOut)
async def fairness(
    intake_id: uuid.UUID, _: Principal = Depends(require("analytics.read")), db: OrgDb = Depends(org_db)
) -> dict[str, Any]:
    return await analytics.fairness(db, intake_id)


@router.get("/lab/intakes", response_model=list[LabIntakeOut])
async def lab_intakes(
    _: Principal = Depends(require("analytics.read")), db: OrgDb = Depends(org_db)
) -> list[dict[str, Any]]:
    return await analytics.lab_intakes(db)


@router.post("/lab", response_model=LabOut)
async def lab(
    body: LabIn, _: Principal = Depends(require("analytics.read")), db: OrgDb = Depends(org_db)
) -> dict[str, Any]:
    return await analytics.lab_report(db, body.intake_ids, body.weights)
