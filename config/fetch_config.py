"""Save the station's current config to config/backup-<timestamp>.json and config/current.json."""

import asyncio
import json
import os
import time

from viam.app.viam_client import ViamClient
from viam.rpc.dial import DialOptions

from station import connect


async def main():
    async with await connect() as machine:
        meta = await machine.get_cloud_metadata()
    print("machine_id", meta.machine_id, "part", meta.machine_part_id,
          "org", meta.primary_org_id, "location", meta.location_id)
    client = await ViamClient.create_from_dial_options(DialOptions.with_api_key(
        os.environ["VIAM_API_KEY"], os.environ["VIAM_API_KEY_ID"]))
    try:
        part = await client.app_client.get_robot_part(meta.machine_part_id)
    finally:
        client.close()
    cfg = part.robot_config
    here = os.path.dirname(__file__)
    for path in (f"backup-{int(time.time())}.json", "current.json"):
        with open(os.path.join(here, path), "w") as f:
            json.dump(cfg, f, indent=2)
    print("saved", len(cfg.get("components", [])), "components,",
          len(cfg.get("services", [])), "services,", len(cfg.get("modules", [])), "modules")


if __name__ == "__main__":
    asyncio.run(main())
