import os
from contextlib import contextmanager
from typing import List, Optional

import psycopg2
from fastapi import FastAPI, Request
from google.protobuf.json_format import MessageToDict
from google.transit import gtfs_realtime_pb2
from pydantic import BaseModel

app = FastAPI()

DB_CONFIG = {
    "host": os.getenv("POSTGRES_HOST", "postgres"),
    "port": int(os.getenv("POSTGRES_PORT", "5432")),
    "dbname": os.getenv("POSTGRES_DB", "mta"),
    "user": os.getenv("POSTGRES_USER", "admin"),
    "password": os.getenv("POSTGRES_PASSWORD", "admin123"),
}


@contextmanager
def get_db():
    conn = psycopg2.connect(**DB_CONFIG)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ── helpers to resolve lookup IDs (get-or-create) ────────────────────────────

def _resolve_lookup(cur, table: str, name: str) -> int:
    cur.execute(
        f"INSERT INTO {table} (name) VALUES (%s) ON CONFLICT (name) DO NOTHING RETURNING id",
        (name,),
    )
    row = cur.fetchone()
    if row:
        return row[0]
    cur.execute(f"SELECT id FROM {table} WHERE name = %s", (name,))
    return cur.fetchone()[0]


def _resolve_route(cur, name: str) -> int:
    return _resolve_lookup(cur, "routes", name)


def _resolve_trip(cur, name: str) -> int:
    return _resolve_lookup(cur, "trips", name)


def _resolve_stop(cur, name: str) -> int:
    return _resolve_lookup(cur, "stops", name)


def _resolve_status(cur, name: str) -> int:
    return _resolve_lookup(cur, "train_statuses", name)


def _direction_from_trip_id(trip_id: str) -> Optional[int]:
    """Infer direction from the trip ID convention: ..N = 0 (north), ..S = 1 (south)."""
    if "..N" in trip_id:
        return 0
    if "..S" in trip_id:
        return 1
    return None


# ── models ───────────────────────────────────────────────────────────────────

class StopTime(BaseModel):
    arrival: Optional[dict] = None
    departure: Optional[dict] = None
    stopId: str


class Trip(BaseModel):
    tripId: str
    startTime: Optional[str] = None
    startDate: Optional[str] = None
    routeId: str


class TripUpdate(BaseModel):
    trip: Trip
    stopTimeUpdate: Optional[List[StopTime]] = None


class Vehicle(BaseModel):
    trip: Trip
    currentStopSequence: Optional[int] = None
    currentStatus: Optional[str] = None
    timestamp: str
    stopId: str


class FeedEntity(BaseModel):
    id: str
    trip_update: Optional[TripUpdate] = None
    vehicle: Optional[Vehicle] = None


# ── endpoints ────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/parse")
async def parse(request: Request):
    body = await request.body()
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.ParseFromString(body)
    return MessageToDict(feed)


@app.post("/save")
async def save(entities: List[FeedEntity]):
    vehicle_count = 0
    time_update_count = 0

    with get_db() as conn:
        cur = conn.cursor()

        for entity in entities:

            # ── vehicle positions ─────────────────────────────────────
            if entity.vehicle:
                v = entity.vehicle
                route_id = _resolve_route(cur, v.trip.routeId)
                trip_id = _resolve_trip(cur, v.trip.tripId)
                stop_id = _resolve_stop(cur, v.stopId)
                status_id = _resolve_status(cur, v.currentStatus) if v.currentStatus else None
                direction = _direction_from_trip_id(v.trip.tripId)

                cur.execute(
                    """
                    INSERT INTO vehicle_positions
                        (route_id, trip_id, stop_id, status_id,
                         current_stop_sequence, start_time, start_date,
                         direction_id, timestamp)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (trip_id, timestamp) DO NOTHING
                    """,
                    (
                        route_id, trip_id, stop_id, status_id,
                        v.currentStopSequence, v.trip.startTime, v.trip.startDate,
                        direction, int(v.timestamp),
                    ),
                )
                vehicle_count += cur.rowcount  # 1 if inserted, 0 if skipped

            # ── time updates (trip updates) ───────────────────────────
            if entity.trip_update and entity.trip_update.stopTimeUpdate:
                tu = entity.trip_update
                route_id = _resolve_route(cur, tu.trip.routeId)
                trip_id = _resolve_trip(cur, tu.trip.tripId)
                direction = _direction_from_trip_id(tu.trip.tripId)

                for stu in tu.stopTimeUpdate:
                    stop_id = _resolve_stop(cur, stu.stopId)
                    arrival = int(stu.arrival["time"]) if stu.arrival and "time" in stu.arrival else None
                    departure = int(stu.departure["time"]) if stu.departure and "time" in stu.departure else None

                    cur.execute(
                        """
                        INSERT INTO time_updates
                            (route_id, trip_id, stop_id,
                             start_time, start_date, direction_id,
                             arrival_time, departure_time)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (trip_id, stop_id, arrival_time) DO NOTHING
                        """,
                        (
                            route_id, trip_id, stop_id,
                            tu.trip.startTime, tu.trip.startDate, direction,
                            arrival, departure,
                        ),
                    )
                    time_update_count += cur.rowcount

        cur.close()

    return {
        "status": "ok",
        "inserted": {
            "vehicle_positions": vehicle_count,
            "time_updates": time_update_count,
        },
    }
