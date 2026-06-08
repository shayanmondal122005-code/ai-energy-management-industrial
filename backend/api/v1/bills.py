"""Bills API — customers upload past electricity bills to calibrate savings + baseline."""
import base64
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database import get_db
from backend.core.security import CurrentUser, get_current_user

logger = logging.getLogger(__name__)
router = APIRouter()

MAX_FILE_BYTES = 8 * 1024 * 1024  # 8 MB cap


class BillIn(BaseModel):
    period: str
    units_kwh: float
    amount_rs: float
    peak_demand_kw: float | None = None
    file_name: str | None = None
    file_base64: str | None = None   # optional bill PDF/image, base64 or data-URL


@router.post("/{facility_id}/bills", status_code=201)
async def upload_bill(
    facility_id: UUID,
    body: BillIn,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Upload one electricity bill (structured fields + optional base64 PDF/image)."""
    if not current_user.can_access_facility(facility_id):
        raise HTTPException(status_code=403, detail="Access denied")

    period = body.period
    units_kwh = body.units_kwh
    amount_rs = body.amount_rs
    peak_demand_kw = body.peak_demand_kw
    file_name = body.file_name
    file_bytes = None
    if body.file_base64:
        try:
            b64 = body.file_base64.split(",")[-1]  # strip data-URL prefix if present
            file_bytes = base64.b64decode(b64)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid file encoding")
        if len(file_bytes) > MAX_FILE_BYTES:
            raise HTTPException(status_code=413, detail="File too large (max 8 MB)")

    row = (await db.execute(
        text("""
            INSERT INTO bills (facility_id, tenant_id, period, units_kwh, peak_demand_kw,
                               amount_rs, file_name, file_data)
            VALUES (:fid, :tid, :period, :units, :demand, :amount, :fname, :fdata)
            RETURNING id, created_at
        """),
        {
            "fid": str(facility_id), "tid": str(current_user.tenant_id),
            "period": period, "units": units_kwh, "demand": peak_demand_kw,
            "amount": amount_rs, "fname": file_name, "fdata": file_bytes,
        },
    )).one()

    logger.info("BILL_UPLOAD facility=%s period=%s units=%s amount=%s", facility_id, period, units_kwh, amount_rs)
    return {
        "id": str(row.id), "period": period, "units_kwh": units_kwh,
        "peak_demand_kw": peak_demand_kw, "amount_rs": amount_rs,
        "file_name": file_name, "has_file": file_bytes is not None,
        "created_at": row.created_at.isoformat(),
        # handy derived metric for the UI
        "effective_rate_rs_kwh": round(amount_rs / units_kwh, 2) if units_kwh else None,
    }


@router.get("/{facility_id}/bills")
async def list_bills(
    facility_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    if not current_user.can_access_facility(facility_id):
        raise HTTPException(status_code=403, detail="Access denied")
    rows = (await db.execute(
        text("""
            SELECT id, period, units_kwh, peak_demand_kw, amount_rs, file_name,
                   (file_data IS NOT NULL) AS has_file, created_at
            FROM bills WHERE facility_id = :fid ORDER BY created_at DESC
        """),
        {"fid": str(facility_id)},
    )).mappings().all()
    out = []
    for r in rows:
        d = dict(r)
        d["id"] = str(d["id"])
        d["created_at"] = d["created_at"].isoformat()
        d["effective_rate_rs_kwh"] = round(d["amount_rs"] / d["units_kwh"], 2) if d["units_kwh"] else None
        out.append(d)
    return out


@router.get("/{facility_id}/bills/{bill_id}/file")
async def download_bill(
    facility_id: UUID,
    bill_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    if not current_user.can_access_facility(facility_id):
        raise HTTPException(status_code=403, detail="Access denied")
    row = (await db.execute(
        text("SELECT file_name, file_data FROM bills WHERE id = :id AND facility_id = :fid"),
        {"id": str(bill_id), "fid": str(facility_id)},
    )).one_or_none()
    if row is None or row.file_data is None:
        raise HTTPException(status_code=404, detail="No file for this bill")
    name = (row.file_name or "bill").lower()
    media = "application/pdf" if name.endswith(".pdf") else "image/jpeg" if name.endswith((".jpg", ".jpeg")) else "image/png" if name.endswith(".png") else "application/octet-stream"
    return Response(bytes(row.file_data), media_type=media,
                    headers={"Content-Disposition": f'inline; filename="{row.file_name or "bill"}"'})
