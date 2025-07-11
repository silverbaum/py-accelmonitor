from fastapi import FastAPI, Depends, Request, Form, UploadFile, File

# from fastapi.middleware.cors import CORSMiddleware
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.encoders import jsonable_encoder

from contextlib import asynccontextmanager
from psycopg2.pool import ThreadedConnectionPool
from fastapi_cache import FastAPICache
from fastapi_cache.decorator import cache
from fastapi_cache.backends.redis import RedisBackend
from redis import asyncio as aioredis

from datetime import datetime
from dotenv import load_dotenv  # .env
from pydantic import BaseModel

import os
import aiofiles  # async file ops for video saving
import tempfile
import csv
import logging


class Tag(BaseModel):
    mac: str
    temperature: float
    humidity: float
    pressure: float
    acceleration_x: float
    acceleration_y: float
    acceleration_z: float
    rssi: int = 0
    timestamp: int = 0


class GatewayData(BaseModel):
    timestamp: int = 0
    coordinates: str = ""
    gwmac: str
    tags: dict[str, Tag]


class GatewayHTTPRequest(BaseModel):
    data: GatewayData


class Video(BaseModel):
    name: str
    start_timestamp: datetime
    video_duration: str
    video_path: str


load_dotenv()


@asynccontextmanager
async def lifespan(_: FastAPI):
    global db_pool
    print("Creating connection pool")
    db_pool = ThreadedConnectionPool(1, 20, os.getenv("DATABASE_URL"))
    with db_pool.getconn() as conn:
        with conn.cursor() as cur:
            cur.execute("""CREATE TABLE IF NOT EXISTS tags (
            id serial PRIMARY KEY,
            mac text,
            temperature numeric,
            humidity numeric,
            pressure numeric,
            acceleration_x numeric NOT NULL,
            acceleration_y numeric NOT NULL,
            acceleration_z numeric NOT NULL,
            created_at timestamptz DEFAULT now()
            );

            CREATE TABLE IF NOT EXISTS videos (
            id serial PRIMARY KEY NOT NULL UNIQUE,
            name text NOT NULL UNIQUE,
            start_timestamp timestamptz NOT NULL,
            video_duration numeric,
            video_path text UNIQUE NOT NULL,
            created_at timestamptz DEFAULT now()
            );
            """)
        conn.commit()

    redis = aioredis.from_url(os.getenv("REDIS_URL"))
    FastAPICache.init(RedisBackend(redis), prefix="fastapi-cache")
    print("Redis cache initialized")

    yield

    print("Closing database connection pool")
    db_pool.closeall()
    print("Closing redis connection")
    await redis.close()


app = FastAPI(lifespan=lifespan)


app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/videos", StaticFiles(directory="videos"), name="videos")
templates = Jinja2Templates(directory="templates")


def get_db():
    if not db_pool:
        raise RuntimeError("Database connection pool not initialized")
    conn = db_pool.getconn()
    try:
        yield conn
    finally:
        db_pool.putconn(conn)


@app.get("/", response_class=HTMLResponse)
async def root(request: Request, db_conn=Depends(get_db)):
    with db_conn.cursor() as cursor:
        cursor.execute("SELECT * FROM videos")
        videos = cursor.fetchall()
        columns = [col[0] for col in cursor.description]
        videos_json = [dict(zip(columns, row)) for row in videos]

    return templates.TemplateResponse(
        request, "index.html", context={"VideoList": jsonable_encoder(videos_json)}
    )


@app.post("/api/tags", status_code=201)
async def create_tag(body: GatewayHTTPRequest, db_conn=Depends(get_db)):
    print(body.data)
    with db_conn.cursor() as cursor:
        try:
            for tag in body.data.tags.values():
                cursor.execute(
                    "INSERT INTO tags (mac, temperature, humidity, pressure, acceleration_x, acceleration_y, acceleration_z) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                    (
                        tag.mac,
                        tag.temperature,
                        tag.humidity,
                        tag.pressure,
                        tag.acceleration_x,
                        tag.acceleration_y,
                        tag.acceleration_z,
                    ),
                )
        except Exception as e:
            logging.exception("Error inserting tags into database", exc_info=e)
            return {
                "message": "Tag creation failed",
                "data": body.data.tags,
                "error": str(e),
            }, 500
    db_conn.commit()
    return {"message": "Tags created", "data": body.data.tags}


@app.get("/api/tags")
@cache(expire=5)
async def get_tags(db_conn=Depends(get_db)):
    with db_conn.cursor() as cursor:
        cursor.execute("SELECT * FROM tags")
        columns = [col[0] for col in cursor.description]
        tags = [dict(zip(columns, row)) for row in cursor.fetchall()]
    return tags, 200


@app.get("/api/tags/range/{start}/{end}")
@cache(expire=720, key_builder=lambda *args, **_: f"tags_range:{args[0]}:{args[1]}")
async def get_tags_range(start: str, end: str, db_conn=Depends(get_db)):
    print(start, end)
    try:
        start_date = datetime.fromisoformat(start)
        end_date = datetime.fromisoformat(end)

        with db_conn.cursor() as cursor:
            cursor.execute(
                "SELECT * FROM tags WHERE created_at BETWEEN %s AND %s",
                (start_date, end_date),
            )
            columns = [col[0] for col in cursor.description]
            tags = [dict(zip(columns, row)) for row in cursor.fetchall()]
    except Exception as e:
        logging.exception("Error retrieving tags in range", exc_info=e)
        return {"message": "Tag retrieval failed", "error": str(e)}, 500
    return tags, 200


@app.get("/api/tags/csv")
async def get_tags_csv(start: str, end: str, db_conn=Depends(get_db)):
    try:
        start_date = datetime.fromisoformat(start)
        end_date = datetime.fromisoformat(end)
        logging.info("start_date:", start_date, "end_date", end_date)

        with db_conn.cursor() as cursor:
            cursor.execute(
                "SELECT * FROM tags WHERE created_at BETWEEN %s AND %s",
                (start_date, end_date),
            )
            columns = [col[0] for col in cursor.description]
            tags = [dict(zip(columns, row)) for row in cursor.fetchall()]
        with tempfile.NamedTemporaryFile(
            delete=False, mode="w", newline=""
        ) as tmp_file:
            writer = csv.DictWriter(tmp_file, fieldnames=columns)
            writer.writeheader()
            for tag in tags:
                writer.writerow(tag)

            return FileResponse(
                tmp_file.name,
                media_type="text/csv",
                filename=f"tags_{start_date.isoformat()}_{end_date.isoformat()}.csv",
            )
    except Exception as e:
        logging.exception("Error generating CSV", exc_info=e)
        return {"message": "Failed to generate CSV", "error": str(e)}, 500


@app.post("/api/videos", status_code=201)
async def save_video(
    video: UploadFile = File(...),
    name: str = Form(...),
    start_timestamp: str = Form(...),
    video_duration: str = Form(...),
    db_conn=Depends(get_db),
):
    try:
        video_path = f"videos/{name}.{video.headers['Content-Type'].split('/')[1]}"
        async with aiofiles.open(video_path, "wb") as out_file:
            while chunk := await video.read(16384):
                await out_file.write(chunk)

        start_time = datetime.fromisoformat(start_timestamp)
        with db_conn.cursor() as cursor:
            cursor.execute(
                "INSERT INTO videos (name, start_timestamp, video_duration, video_path) VALUES(%s, %s, %s, %s)",
                (str(name), start_time, video_duration, video_path),
            )
            db_conn.commit()

        return {
            "message": "Video saved",
            "data": {
                "name": name,
                "start_timestamp": start_timestamp,
                "video_duration": video_duration,
                "video_path": video_path,
            },
        }
    except Exception as e:
        logging.exception("Error saving video", exc_info=e)
        return {"message": "Failed to save video", "error": str(e)}, 500


@app.delete("/api/videos/{video_name}", status_code=304)
async def delete_video(video_name: str, db_conn=Depends(get_db)):
    try:
        with db_conn.cursor() as cursor:
            video = video_name.split(".")[0]
            cursor.execute("DELETE FROM videos WHERE name = %s", (video,))
            db_conn.commit()

        video_path = f"./videos/{video_name}"
        if os.path.exists(video_path):
            os.remove(video_path)

        return {"message": "Video deleted"}
    except Exception as e:
        logging.exception("Error deleting video", exc_info=e)
        return {"message": "Failed to delete video", "error": str(e)}, 500
