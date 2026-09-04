import os

import redis
from dotenv import load_dotenv

load_dotenv()

r = redis.Redis(
    host=os.environ["REDIS_HOST"],
    port=int(os.environ["REDIS_PORT"]),
    password=os.environ["REDIS_PASSWORD"],
    decode_responses=True,
)