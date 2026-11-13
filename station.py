"""Connection to the hackathon station. Credentials come from .env (see .gitignore)."""

import os

from dotenv import load_dotenv
from viam.robot.client import RobotClient

load_dotenv()


async def connect() -> RobotClient:
    opts = RobotClient.Options.with_api_key(
        api_key=os.environ["VIAM_API_KEY"],
        api_key_id=os.environ["VIAM_API_KEY_ID"],
    )
    return await RobotClient.at_address(os.environ["VIAM_ADDRESS"], opts)
