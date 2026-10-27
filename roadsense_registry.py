    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return radius * 2 * atan2(sqrt(a), sqrt(1 - a))


class PotholeReport(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    confidence: float = Field(ge=0, le=1)
    class_id: int | None = None
    source_vehicle: str | None = Field(default=None, max_length=100)


def serialize(row):
    return {key: row[key] for key in (
        "id", "latitude", "longitude", "confidence", "class_id",
        "source_vehicle", "first_seen", "last_seen", "expires_at",
        "observation_count"
    )}


@app.on_event("startup")
def startup():
    initialize_database()
    purge_expired()


@app.get("/")
def root():
    return {"service": "RoadSense Pothole Registry", "status": "running", "docs": "/docs", "health": "/health"}


@app.get("/health")
def health():
    initialize_database()
    purge_expired()
    return {"status": "ok", "database": str(DB_PATH), "retention_days": RETENTION_DAYS}


@app.post("/potholes")
def register_pothole(report: PotholeReport):
    initialize_database()
    purge_expired()
    now_dt = utc_now()
    now = iso(now_dt)
    expires = iso(now_dt + timedelta(days=RETENTION_DAYS))

    with connect() as conn:
        rows = conn.execute("SELECT * FROM potholes WHERE expires_at > ?", (now,)).fetchall()
        nearest = None
        nearest_distance = None

        for row in rows:
            distance = distance_meters(report.latitude, report.longitude, row["latitude"], row["longitude"])
            if distance <= DUPLICATE_RADIUS_METERS and (nearest_distance is None or distance < nearest_distance):
                nearest, nearest_distance = row, distance

        if nearest is not None:
            conn.execute(
                """UPDATE potholes
                   SET last_seen = ?, expires_at = ?, observation_count = observation_count + 1,
                       confidence = MAX(confidence, ?),
                       source_vehicle = COALESCE(?, source_vehicle)
                   WHERE id = ?""",
                (now, expires, report.confidence, report.source_vehicle, nearest["id"]),
            )
            conn.commit()
            updated = conn.execute("SELECT * FROM potholes WHERE id = ?", (nearest["id"],)).fetchone()
            return {
                "status": "duplicate",
                "message": "Nearby pothole already exists; observation updated.",
                "distance_meters": round(nearest_distance, 2),
                "pothole": serialize(updated),
            }

        cursor = conn.execute(
            """INSERT INTO potholes
               (latitude, longitude, confidence, class_id, source_vehicle, first_seen, last_seen, expires_at, observation_count)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)""",
            (report.latitude, report.longitude, report.confidence, report.class_id,
             report.source_vehicle, now, now, expires),
        )
        conn.commit()
        created = conn.execute("SELECT * FROM potholes WHERE id = ?", (cursor.lastrowid,)).fetchone()

    return {"status": "registered", "message": "New pothole registered.", "pothole": serialize(created)}


@app.get("/potholes")
def list_potholes(limit: int = Query(default=500, ge=1, le=5000)):
    initialize_database()
    purge_expired()
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM potholes WHERE expires_at > ? ORDER BY last_seen DESC LIMIT ?",
            (iso(utc_now()), limit),
        ).fetchall()
    return {"count": len(rows), "potholes": [serialize(row) for row in rows]}


@app.get("/potholes/{pothole_id}")
def get_pothole(pothole_id: int):
    initialize_database()
    purge_expired()
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM potholes WHERE id = ? AND expires_at > ?",
            (pothole_id, iso(utc_now())),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Pothole not found or expired.")
    return serialize(row)


@app.delete("/potholes/{pothole_id}")
def delete_pothole(pothole_id: int):
    # Prototype only: add authentication before exposing this endpoint publicly.
    initialize_database()
    with connect() as conn:
        cursor = conn.execute("DELETE FROM potholes WHERE id = ?", (pothole_id,))
        conn.commit()
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Pothole not found.")
    return {"status": "deleted", "id": pothole_id}
