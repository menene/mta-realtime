import logging
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any, List, Optional

import psycopg2
import requests as http_requests
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from google.protobuf.json_format import MessageToDict
from google.transit import gtfs_realtime_pb2
from jinja2 import Environment, FileSystemLoader
from pydantic import BaseModel, model_validator

logger = logging.getLogger("mta")

app = FastAPI()

# ── NiFi proxy configuration ─────────────────────────────────────────────────

NIFI_HOST = os.getenv("NIFI_HOST", "http://nifi:8080")
NIFI_USERNAME = os.getenv("NIFI_USERNAME", "admin")
NIFI_PASSWORD = os.getenv("NIFI_PASSWORD", "adminpassword123")


def _nifi_headers() -> dict:
    """Return auth headers for NiFi. Skips token auth when NiFi runs over HTTP."""
    if NIFI_HOST.startswith("https"):
        resp = http_requests.post(
            f"{NIFI_HOST}/nifi-api/access/token",
            data={"username": NIFI_USERNAME, "password": NIFI_PASSWORD},
            timeout=10,
        )
        resp.raise_for_status()
        return {"Authorization": f"Bearer {resp.text}"}
    return {}


def _root_process_group_id() -> str:
    """Get the root process group ID from NiFi."""
    headers = _nifi_headers()
    resp = http_requests.get(
        f"{NIFI_HOST}/nifi-api/flow/process-groups/root",
        headers=headers,
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()["processGroupFlow"]["id"]

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


# ── NiFi control endpoints ───────────────────────────────────────────────────

@app.get("/nifi/status")
def nifi_status():
    """Return the current NiFi root process group flow state."""
    try:
        headers = _nifi_headers()
        pg_id = _root_process_group_id()
        resp = http_requests.get(
            f"{NIFI_HOST}/nifi-api/flow/process-groups/{pg_id}/status",
            headers=headers,
            timeout=10,
        )
        resp.raise_for_status()
        agg = resp.json()["processGroupStatus"]["aggregateSnapshot"]
        running = agg.get("activeThreadCount", 0)
        queued = agg.get("flowFilesQueued", 0)

        # Check if any processors are running
        flow_resp = http_requests.get(
            f"{NIFI_HOST}/nifi-api/flow/process-groups/{pg_id}",
            headers=headers,
            timeout=10,
        )
        flow_resp.raise_for_status()
        processors = flow_resp.json()["processGroupFlow"]["flow"].get("processors", [])
        any_running = any(
            p["status"]["runStatus"] == "Running" for p in processors
        )
        state = "RUNNING" if any_running else "STOPPED"
        return {"state": state, "activeThreads": running, "queued": queued}
    except Exception as exc:
        logger.exception("Failed to get NiFi status")
        raise HTTPException(status_code=502, detail=str(exc))


@app.put("/nifi/start")
def nifi_start():
    """Start all processors in the NiFi root process group."""
    try:
        headers = _nifi_headers()
        pg_id = _root_process_group_id()
        resp = http_requests.put(
            f"{NIFI_HOST}/nifi-api/flow/process-groups/{pg_id}",
            headers=headers,
            json={"id": pg_id, "state": "RUNNING"},
            timeout=10,
        )
        resp.raise_for_status()
        return {"state": "RUNNING"}
    except Exception as exc:
        logger.exception("Failed to start NiFi flow")
        raise HTTPException(status_code=502, detail=str(exc))


@app.put("/nifi/stop")
def nifi_stop():
    """Stop all processors in the NiFi root process group."""
    try:
        headers = _nifi_headers()
        pg_id = _root_process_group_id()
        resp = http_requests.put(
            f"{NIFI_HOST}/nifi-api/flow/process-groups/{pg_id}",
            headers=headers,
            json={"id": pg_id, "state": "STOPPED"},
            timeout=10,
        )
        resp.raise_for_status()
        return {"state": "STOPPED"}
    except Exception as exc:
        logger.exception("Failed to stop NiFi flow")
        raise HTTPException(status_code=502, detail=str(exc))


@app.post("/parse")
async def parse(request: Request):
    body = await request.body()
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.ParseFromString(body)
    return MessageToDict(feed)


@app.post("/ingest")
async def ingest(request: Request):
    """Parse raw protobuf and save to DB in one step."""
    body = await request.body()
    proto = gtfs_realtime_pb2.FeedMessage()
    proto.ParseFromString(body)
    feed_dict = MessageToDict(proto)
    feed = FeedMessage.model_validate(_snake_to_camel(feed_dict))
    return await save(feed)


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
                                ON CONFLICT DO NOTHING
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
