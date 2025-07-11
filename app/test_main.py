from fastapi.testclient import TestClient
from psycopg2.pool import ThreadedConnectionPool

from fastapi_cache import FastAPICache
from fastapi_cache.backends.redis import RedisBackend
from redis import asyncio as aioredis

from dotenv import load_dotenv
from os import getenv
from random import randint

from pytest import fixture

import datetime
from .main import app, get_db

load_dotenv()


@fixture
def setup_test_db():
    global db_test_pool
    db_test_pool = ThreadedConnectionPool(1, 10, getenv("TEST_DATABASE_URL"))
    conn = db_test_pool.getconn()
    c = conn.cursor()
    c.execute("""
    CREATE TABLE IF NOT EXISTS tags (
        id SERIAL PRIMARY KEY,
        mac TEXT NOT NULL,
        temperature NUMERIC,
        humidity NUMERIC,
        pressure NUMERIC,
        acceleration_x NUMERIC NOT NULL,
        acceleration_y NUMERIC NOT NULL,
        acceleration_z NUMERIC NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now());
    CREATE TABLE IF NOT EXISTS videos (
        id serial PRIMARY KEY,
        name text,
        start_timestamp timestamptz,
        video_duration text,
        video_path text
        );
    """)
    c.execute("CREATE INDEX IF NOT EXISTS tags_mac_idx ON tags (mac)")
    conn.commit()
    conn.close()
    db_test_pool.putconn(conn)

    redis = aioredis.from_url(getenv("REDIS_URL"))
    FastAPICache.init(RedisBackend(redis), prefix="fastapi-cache")

    try:
        yield db_test_pool
    finally:
        conn = db_test_pool.getconn()
        conn.cursor().execute("DELETE FROM tags; DELETE FROM videos;")
        conn.commit()
        conn.close()
        db_test_pool.closeall()
        close = redis.close()
        close.close()


def get_test_db():
    conn = db_test_pool.getconn()
    yield conn


client = TestClient(app)


app.dependency_overrides[get_db] = get_test_db


def test_root(setup_test_db):
    response = client.get("/")
    assert response.status_code == 200


def test_create_tag(setup_test_db):
    mac = "12:34:56:78:90:AB"
    tag_data = {
        "mac": mac,
        "temperature": randint(0, 30),
        "humidity": randint(0, 100),
        "pressure": randint(90000, 101300),
        "acceleration_x": randint(-1000, 1000),
        "acceleration_y": randint(-1000, 1000),
        "acceleration_z": randint(-1000, 1000),
        "rssi": None,
        "timestamp": None
    }

    payload = {"data": {"gwmac": mac, "timestamp": datetime.datetime.now().timestamp(), "coordinates": "", "tags": {mac: tag_data}}}
    response = client.post("/api/tags", json=payload)
    data: dict = response.json()
    
    assert response.status_code == 201
    assert data["message"] == "Tags created"
    assert data["data"][mac] == tag_data


def test_tags_range(setup_test_db):
    start = datetime.datetime.now().isoformat()
    end = datetime.datetime.now()
    if end.minute < 50:
        end.replace(minute=end.minute + 10)
    else:
        end.replace(minute=end.minute - 10)
    response = client.get(f"/api/tags/range/{start}/{end}")
    assert response.is_success
