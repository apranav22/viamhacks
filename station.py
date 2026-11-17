"""Connection to the hackathon station. Credentials come from .env (see .gitignore)."""

import os

from dotenv import load_dotenv
from viam.robot.client import RobotClient

load_dotenv()


def credentials() -> dict:
    """.env (VIAM_ADDRESS, VIAM_API_KEY, VIAM_API_KEY_ID), else api-key.json next to this file."""
    if os.environ.get("VIAM_API_KEY"):
        return {"address": os.environ["VIAM_ADDRESS"], "api_key": os.environ["VIAM_API_KEY"],
                "api_key_id": os.environ["VIAM_API_KEY_ID"]}
    import json
    return json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "api-key.json")))


async def connect() -> RobotClient:
    c = credentials()
    opts = RobotClient.Options.with_api_key(api_key=c["api_key"], api_key_id=c["api_key_id"])
    return await RobotClient.at_address(c["address"], opts)
