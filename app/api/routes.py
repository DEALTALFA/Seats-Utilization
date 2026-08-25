"""HTTP routes for seats, occupancy and utilization reporting."""

from datetime import date

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import ValidationError

from app.api.deps import StoreDep
from app.models import (
    DailyUtilization,
    DateRange,
    OccupancyCreate,
    OccupancyRecord,
    Seat,
    UtilizationSummary,
)
from app.services.utilization import UnknownSeatError

router = APIRouter()

FloorQuery = Query(default=None, description="Restrict results to a single floor")

# Spelled out rather than taken from `status`: Starlette renamed the 422
# constant, so the literal keeps us off both the old and the new name.
HTTP_422 = 422


def _period(start: date, end: date) -> DateRange:
    try:
        return DateRange(start=start, end=end)
    except ValidationError as exc:
        raise HTTPException(
            status_code=HTTP_422,
            detail="end must not be earlier than start",
        ) from exc


@router.get("/seats", response_model=list[Seat], tags=["seats"])
def list_seats(store: StoreDep, floor: str | None = FloorQuery) -> list[Seat]:
    return store.list_seats(floor=floor)


@router.get("/seats/{seat_id}", response_model=Seat, tags=["seats"])
def get_seat(seat_id: str, store: StoreDep) -> Seat:
    try:
        return store.get_seat(seat_id)
    except UnknownSeatError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post(
    "/occupancy",
    response_model=OccupancyRecord,
    status_code=status.HTTP_201_CREATED,
    tags=["occupancy"],
)
def record_occupancy(payload: OccupancyCreate, store: StoreDep) -> OccupancyRecord:
    try:
        return store.record_occupancy(payload)
    except UnknownSeatError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/utilization", response_model=UtilizationSummary, tags=["reporting"])
def utilization(
    store: StoreDep,
    start: date,
    end: date,
    floor: str | None = FloorQuery,
) -> UtilizationSummary:
    return store.summarize(_period(start, end), floor=floor)


@router.get("/utilization/daily", response_model=list[DailyUtilization], tags=["reporting"])
def utilization_daily(
    store: StoreDep,
    start: date,
    end: date,
    floor: str | None = FloorQuery,
) -> list[DailyUtilization]:
    return store.daily_breakdown(_period(start, end), floor=floor)
