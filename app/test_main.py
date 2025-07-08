from fastapi.testclient import TestClient
from psycopg2.pool import ThreadedConnectionPool

from dotenv import load_dotenv
load_dotenv()
from os import getenv
from random import randint

from pytest import fixture

from .main import app, get_db

db_test_pool = None

@fixture
def setup_test_db():
    global db_test_pool
    db_test_pool = ThreadedConnectionPool(1, 10, getenv("TEST_DATABASE_URL"))
    conn = db_test_pool.getconn()
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS tags (\
        id SERIAL PRIMARY KEY,\
        mac VARCHAR(20) NOT NULL,\
        temperature NUMERIC,\
        humidity NUMERIC,\
        pressure NUMERIC,\
        acceleration_x NUMERIC NOT NULL,\
        acceleration_y NUMERIC NOT NULL,\
        acceleration_z NUMERIC NOT NULL,\
        created_at TIMESTAMPTZ NOT NULL DEFAULT now())")
    c.execute("CREATE INDEX IF NOT EXISTS tags_mac_idx ON tags (mac)")
    conn.commit()
    conn.close()
    db_test_pool.putconn(conn)
    try:
        yield db_test_pool
    finally:
        conn = db_test_pool.getconn()
        conn.cursor().execute("DELETE FROM tags")
        conn.commit()
        conn.close()
        db_test_pool.closeall()
     


def get_test_db():
        return db_test_pool.getconn()

client = TestClient(app)


app.dependency_overrides[get_db] = get_test_db

def test_root():
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"message": "Hello from the tags API!"}


def test_create_tag(setup_test_db):
    mac = "12:34:56:78:90:AB"
    tag_data = {
        "mac": mac,
        "temperature": randint(0, 30),
        "humidity": randint(0, 100),
        "pressure": randint(90000, 101300),
        "acceleration_x": randint(-1000, 1000),
        "acceleration_y": randint(-1000, 1000),
        "acceleration_z": randint(-1000, 1000)
    }

    payload = {
        "data": {
            "gwmac": mac,
            "tags": {
                mac: tag_data
            }
        }
    }
    response = client.post("/tags/new", json=payload)
    assert response.status_code == 201
    assert response.json() == {
        "message": "Tags created",
        "data": {
            mac: tag_data
        }
    }