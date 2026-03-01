from fastapi import FastAPI, Request, Response

from google.protobuf.json_format import MessageToDict
from google.transit import gtfs_realtime_pb2

app = FastAPI()


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/parse")
async def parse(request: Request):
    body = await request.body()
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.ParseFromString(body)
    return MessageToDict(feed)
