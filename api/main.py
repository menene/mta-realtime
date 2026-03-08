import logging
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any, List, Optional

import psycopg2
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from google.protobuf.json_format import MessageToDict
from google.transit import gtfs_realtime_pb2
from jinja2 import Environment, FileSystemLoader
from pydantic import BaseModel, model_validator

logger = logging.getLogger("mta")

app = FastAPI()

# ── docs / static files ──────────────────────────────────────────────────────

_BASE_DIR = Path(__file__).resolve().parent
_templates = Environment(loader=FileSystemLoader(_BASE_DIR / "templates"))

_docs_dir = Path("/app/docs")
if _docs_dir.is_dir():
    app.mount("/static", StaticFiles(directory=str(_docs_dir)), name="static")

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

def _snake_to_camel(data: Any) -> Any:
    """Recursively convert snake_case keys to camelCase in dicts."""
    if isinstance(data, dict):
        out = {}
        for k, v in data.items():
            parts = k.split("_")
            camel = parts[0] + "".join(p.capitalize() for p in parts[1:])
            out[camel] = _snake_to_camel(v)
        return out
    if isinstance(data, list):
        return [_snake_to_camel(i) for i in data]
    return data


class StopTime(BaseModel):
    arrival: Optional[dict] = None
    departure: Optional[dict] = None
    stopId: Optional[str] = None


class Trip(BaseModel):
    tripId: Optional[str] = None
    startTime: Optional[str] = None
    startDate: Optional[str] = None
    routeId: Optional[str] = None


class TripUpdate(BaseModel):
    trip: Optional[Trip] = None
    stopTimeUpdate: Optional[List[StopTime]] = None


class Vehicle(BaseModel):
    trip: Optional[Trip] = None
    currentStopSequence: Optional[int] = None
    currentStatus: Optional[str] = None
    timestamp: Optional[str] = None
    stopId: Optional[str] = None


class FeedEntity(BaseModel):
    id: str
    tripUpdate: Optional[TripUpdate] = None
    vehicle: Optional[Vehicle] = None

    @model_validator(mode="before")
    @classmethod
    def _normalise_keys(cls, values: Any) -> Any:
        if isinstance(values, dict):
            return _snake_to_camel(values)
        return values


class FeedMessage(BaseModel):
    header: Optional[dict] = None
    entity: List[FeedEntity] = []

    @model_validator(mode="before")
    @classmethod
    def _accept_bare_list(cls, values: Any) -> Any:
        """Accept a bare entity list as well as a full FeedMessage."""
        if isinstance(values, list):
            return {"entity": values}
        return values


# ── endpoints ────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
def docs_page():
    template = _templates.get_template("docs.html")
    return template.render()


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
async def save(feed: FeedMessage):
    entities = feed.entity
    vehicle_count = 0
    time_update_count = 0
    skipped = 0
    errors = 0

    with get_db() as conn:
        cur = conn.cursor()

        for idx, entity in enumerate(entities):
            try:
                cur.execute(f"SAVEPOINT sp_{idx}")

                # ── vehicle positions ─────────────────────────────────
                if entity.vehicle:
                    v = entity.vehicle
                    if not (v.trip and v.trip.tripId and v.trip.routeId and v.stopId and v.timestamp):
                        logger.debug("Skipping vehicle entity %s: missing required fields", entity.id)
                        skipped += 1
                    else:
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
                        vehicle_count += cur.rowcount

                # ── time updates (trip updates) ───────────────────────
                if entity.tripUpdate and entity.tripUpdate.stopTimeUpdate:
                    tu = entity.tripUpdate
                    if not (tu.trip and tu.trip.tripId and tu.trip.routeId):
                        logger.debug("Skipping tripUpdate entity %s: missing required fields", entity.id)
                        skipped += 1
                    else:
                        route_id = _resolve_route(cur, tu.trip.routeId)
                        trip_id = _resolve_trip(cur, tu.trip.tripId)
                        direction = _direction_from_trip_id(tu.trip.tripId)

                        for stu in tu.stopTimeUpdate:
                            if not stu.stopId:
                                continue
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

            except Exception:
                logger.exception("Error processing entity %s", entity.id)
                errors += 1
                cur.execute(f"ROLLBACK TO SAVEPOINT sp_{idx}")

        cur.close()

    logger.info(
        "save complete: vehicles=%d, time_updates=%d, skipped=%d, errors=%d",
        vehicle_count, time_update_count, skipped, errors,
    )
    return {
        "status": "ok",
        "inserted": {
            "vehicle_positions": vehicle_count,
            "time_updates": time_update_count,
        },
        "skipped": skipped,
        "errors": errors,
    }
