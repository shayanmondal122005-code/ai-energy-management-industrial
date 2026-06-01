"""Reports API — trigger and retrieve generated PDF reports."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database import get_db
from backend.core.security import CurrentUser, get_current_user

router = APIRouter()


@router.post("/{facility_id}/reports/weekly", status_code=202)
async def trigger_weekly_report(
    facility_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Queue a weekly PDF report for generation (async job)."""
    if not current_user.can_access_facility(facility_id):
        raise HTTPException(status_code=403, detail="Access denied")
    current_user.require_admin()

    # TODO: enqueue report generation job
    return {"status": "queued", "facility_id": str(facility_id), "message": "Report will be ready within 10 minutes"}


@router.get("/{facility_id}/reports")
async def list_reports(
    facility_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    if not current_user.can_access_facility(facility_id):
        raise HTTPException(status_code=403, detail="Access denied")
    # TODO: query reports table
    return []
