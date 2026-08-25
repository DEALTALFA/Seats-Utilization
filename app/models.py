"""Request, response and domain models."""

from datetime import date

from pydantic import BaseModel, Field, model_validator


class Seat(BaseModel):
    """A bookable desk in the office."""

    id: str
    floor: str
    zone: str


class OccupancyRecord(BaseModel):
    """Whether a seat was used on a particular day."""

    seat_id: str
    day: date
    occupied: bool


class OccupancyCreate(BaseModel):
    """Payload for recording (or correcting) a single seat-day."""

    seat_id: str
    day: date
    occupied: bool = True


class DailyUtilization(BaseModel):
    day: date
    seat_count: int
    occupied: int
    utilization_rate: float


class UtilizationSummary(BaseModel):
    """Aggregate utilization over a closed date range."""

    start: date
    end: date
    floor: str | None = None
    seat_count: int
    seat_days: int = Field(description="seat_count multiplied by the number of days in range")
    occupied_seat_days: int
    utilization_rate: float
    target_utilization: float
    meets_target: bool


class DateRange(BaseModel):
    """Validated inclusive date range used by the reporting endpoints."""

    start: date
    end: date

    @model_validator(mode="after")
    def check_order(self) -> "DateRange":
        if self.end < self.start:
            raise ValueError("end must not be earlier than start")
        return self

    @property
    def days(self) -> int:
        return (self.end - self.start).days + 1
