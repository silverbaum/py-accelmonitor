from fastapi import FastAPI, Depends, Request, Form, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.encoders import jsonable_encoder

from pydantic import BaseModel
from contextlib import asynccontextmanager

from psycopg2.pool import ThreadedConnectionPool
from fastapi_cache import FastAPICache
from fastapi_cache.decorator import cache
from fastapi_cache.backends.redis import RedisBackend
from redis import asyncio as aioredis

from datetime import datetime
from os import getenv
from dotenv import load_dotenv

load_dotenv()

import aiofiles
import json

db_pool = None

@asynccontextmanager
async def lifespan(_: FastAPI):
    global db_pool
    print("Creating connection pool")
    db_pool = ThreadedConnectionPool(1, 10, getenv("DATABASE_URL"))

    redis = aioredis.from_url(getenv("REDIS_URL"))
    FastAPICache.init(RedisBackend(redis), prefix="fastapi-cache")
    print("Redis cache initialized")

    yield

    print("Closing database connection pool")
    db_pool.closeall()
    print("Closing redis connection")
    await redis.close()


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # !!, change to frontend url
    allow_methods=["*"],
    allow_headers=["*"],
)

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


class Tag(BaseModel):
    mac: str
    temperature: float
    humidity: float
    pressure: float
    acceleration_x: float
    acceleration_y: float
    acceleration_z: float

class GatewayData(BaseModel):
    gwmac: str
    tags: dict[str, Tag]

class GatewayHTTPRequest(BaseModel):
    data: GatewayData

class Video (BaseModel):
    name:            str
    start_timestamp: datetime
    video_duration:  str
    video_path:      str

class VideoForm(BaseModel):
    name: str
    start_timestamp: str
    video_duration: str

@app.get("/", response_class=HTMLResponse)
async def root(request: Request, db_conn = Depends(get_db)):
        with db_conn.cursor() as cursor:
            cursor.execute("SELECT * FROM videos")
            videos = cursor.fetchall()
            columns = [col[0] for col in cursor.description]
            videos_json = [dict(zip(columns, row)) for row in videos]
            

        return templates.TemplateResponse(
            request, "index.html", context={"VideoList": jsonable_encoder(videos_json)}
        )
    

@app.post("/tags", status_code=201)
async def create_tag(body: GatewayHTTPRequest, db_conn = Depends(get_db)):
    print(body.data)
    with db_conn.cursor() as cursor:
        try:
            for tag in body.data.tags.values():
                cursor.execute("INSERT INTO tags (mac, temperature, humidity, pressure, acceleration_x, acceleration_y, acceleration_z) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                            (tag.mac, tag.temperature, tag.humidity, tag.pressure, tag.acceleration_x, tag.acceleration_y, tag.acceleration_z))
        except Exception as e:
            print(e)
            return {"message": "Tag creation failed", "data": body.data.tags, "error": str(e)}, 500
    db_conn.commit()
    return {"message": "Tags created", "data": body.data.tags}


@app.get("/tags")
@cache(expire=5)
async def get_tags(db_conn = Depends(get_db)):
    with db_conn.cursor() as cursor:
        cursor.execute("SELECT * FROM tags")
        columns = [col[0] for col in cursor.description]
        tags = [dict(zip(columns, row)) for row in cursor.fetchall()]
    return tags, 200


@app.get("/tags/range/{start}/{end}")
@cache(expire=720, key_builder=lambda *args, **_: f"tags_range:{args[0]}:{args[1]}")
async def get_tags_range(start: str, end: str, db_conn = Depends(get_db)):
    print(start, end)
    try:
        start_date = datetime.fromisoformat(start)
        end_date = datetime.fromisoformat(end)
 
        with db_conn.cursor() as cursor:
            
                cursor.execute("SELECT * FROM tags WHERE created_at BETWEEN %s AND %s", (start_date, end_date))
                columns = [col[0] for col in cursor.description]
                tags = [dict(zip(columns, row)) for row in cursor.fetchall()]
    except Exception as e:
        print(e)
        return {"message": "Tag retrieval failed", "error": str(e)}, 500
    return tags, 200

@app.post("/videos", status_code=201)
async def save_video(
        video: UploadFile = File(...),
        name: str = Form(...),
        start_timestamp: str = Form(...),
        video_duration: str = Form(...),
        db_conn = Depends(get_db)):
    try:
        video_path = f"videos/{name}.{video.headers['Content-Type'].split('/')[1]}"
        async with aiofiles.open(video_path, 'wb') as out_file:
            while chunk := await video.read(16384):
                await out_file.write(chunk)
        
        start_time = datetime.fromisoformat(start_timestamp)
        with db_conn.cursor() as cursor:
            cursor.execute("INSERT INTO videos (name, start_timestamp, video_duration, video_path) VALUES(%s, %s, %s, %s)", 
                           (str(name), start_time, video_duration, video_path))
            db_conn.commit()
            
        return {"message": "Video saved", "data": {"name": name, "start_timestamp": start_timestamp, "video_duration": video_duration, "video_path": video_path}}
    except Exception as e:
        print(e)
        return {"message": "Failed to save video", "error": str(e)}, 500

