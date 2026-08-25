"""In-memory seat and occupancy store plus the utilization calculations.

Deliberately not backed by a database: the point of this service is the
reporting logic and the delivery pipeline around it. Swapping `SeatStore` for a
repository over Postgres would not change the API surface.
"""

from datetime import date, timedelta

from app.models import (
    DailyUtilization,
    DateRange,
    OccupancyCreate,
    OccupancyRecord,
    Seat,
    UtilizationSummary,
)

FLOORS = ("1", "2", "3")
ZONES = ("north", "south", "quiet")
SEATS_PER_ZONE = 8


class UnknownSeatError(LookupError):
    """Raised when an occupancy record references a seat that does not exist."""

    def __init__(self, seat_id: str) -> None:
        super().__init__(f"unknown seat: {seat_id}")
        self.seat_id = seat_id


class SeatStore:
    def __init__(self, seats: list[Seat], target_utilization: float = 0.75) -> None:
        self._seats: dict[str, Seat] = {seat.id: seat for seat in seats}
        self._occupancy: dict[tuple[str, date], bool] = {}
        self.target_utilization = target_utilization

    # -- seats -------------------------------------------------------------

    def list_seats(self, floor: str | None = None) -> list[Seat]:
        seats = list(self._seats.values())
        if floor is not None:
            seats = [seat for seat in seats if seat.floor == floor]
        return sorted(seats, key=lambda seat: seat.id)

    def get_seat(self, seat_id: str) -> Seat:
        try:
            return self._seats[seat_id]
        except KeyError:
            raise UnknownSeatError(seat_id) from None

    # -- occupancy ---------------------------------------------------------

    def record_occupancy(self, payload: OccupancyCreate) -> OccupancyRecord:
        """Upsert a single seat-day. Re-recording the same key overwrites it."""
        self.get_seat(payload.seat_id)
        self._occupancy[(payload.seat_id, payload.day)] = payload.occupied
        return OccupancyRecord(seat_id=payload.seat_id, day=payload.day, occupied=payload.occupied)

    def occupied_count(self, day: date, seat_ids: set[str]) -> int:
        return sum(
            1
            for (seat_id, recorded_day), occupied in self._occupancy.items()
            if occupied and recorded_day == day and seat_id in seat_ids
        )

    # -- reporting ---------------------------------------------------------

    def summarize(self, period: DateRange, floor: str | None = None) -> UtilizationSummary:
        seats = self.list_seats(floor=floor)
        seat_ids = {seat.id for seat in seats}
        seat_days = len(seats) * period.days
        occupied = sum(
            self.occupied_count(day, seat_ids) for day in _walk(period.start, period.end)
        )
        rate = occupied / seat_days if seat_days else 0.0
        return UtilizationSummary(
            start=period.start,
            end=period.end,
            floor=floor,
            seat_count=len(seats),
            seat_days=seat_days,
            occupied_seat_days=occupied,
            utilization_rate=round(rate, 4),
            target_utilization=self.target_utilization,
            meets_target=rate >= self.target_utilization,
        )

    def daily_breakdown(
        self, period: DateRange, floor: str | None = None
    ) -> list[DailyUtilization]:
        seats = self.list_seats(floor=floor)
        seat_ids = {seat.id for seat in seats}
        breakdown = []
        for day in _walk(period.start, period.end):
            occupied = self.occupied_count(day, seat_ids)
            rate = occupied / len(seats) if seats else 0.0
            breakdown.append(
                DailyUtilization(
                    day=day,
                    seat_count=len(seats),
                    occupied=occupied,
                    utilization_rate=round(rate, 4),
                )
            )
        return breakdown


def _walk(start: date, end: date) -> list[date]:
    return [start + timedelta(days=offset) for offset in range((end - start).days + 1)]


def default_seats() -> list[Seat]:
    """A deterministic floor plan: 3 floors x 3 zones x 8 seats."""
    return [
        Seat(id=f"{floor}-{zone[:1].upper()}{index:02d}", floor=floor, zone=zone)
        for floor in FLOORS
        for zone in ZONES
        for index in range(1, SEATS_PER_ZONE + 1)
    ]


def build_store(
    target_utilization: float = 0.75,
    seed_history_days: int = 0,
    today: date | None = None,
) -> SeatStore:
    """Build a store, optionally pre-filled with deterministic demo history.

    The seeded pattern skips weekends and leaves every fourth seat-day empty, so
    the sample data lands a little under a 0.75 target instead of being flat.
    """
    store = SeatStore(default_seats(), target_utilization=target_utilization)
    if seed_history_days <= 0:
        return store

    anchor = today or date.today()
    seats = store.list_seats()
    for day_offset in range(seed_history_days):
        day = anchor - timedelta(days=day_offset)
        if day.weekday() >= 5:  # Saturday/Sunday
            continue
        for seat_index, seat in enumerate(seats):
            occupied = (seat_index + day.toordinal()) % 4 != 0
            store.record_occupancy(OccupancyCreate(seat_id=seat.id, day=day, occupied=occupied))
    return store
