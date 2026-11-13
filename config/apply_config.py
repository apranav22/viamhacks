"""Merge config/additions.json into the station's live config.

Entries are matched by name: an existing entry with the same name is replaced, anything else
is appended, and nothing already on the machine is removed. The config as it was is saved to
config/backup-<timestamp>.json first. Pass --dry-run to print the merged config without writing.
"""

import argparse
import asyncio
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from viam.app.viam_client import ViamClient
from viam.rpc.dial import DialOptions

from station import connect

HERE = os.path.dirname(os.path.abspath(__file__))


def merge(cfg: dict, additions: dict) -> dict:
    for section, entries in additions.items():
        existing = cfg.setdefault(section, [])
        for entry in entries:
            existing[:] = [e for e in existing if e.get("name") != entry["name"]]
            existing.append(entry)
    return cfg


async def main(dry_run: bool):
    async with await connect() as machine:
        meta = await machine.get_cloud_metadata()
    client = await ViamClient.create_from_dial_options(DialOptions.with_api_key(
        os.environ["VIAM_API_KEY"], os.environ["VIAM_API_KEY_ID"]))
    try:
        part = await client.app_client.get_robot_part(meta.machine_part_id)
        cfg = part.robot_config
        with open(os.path.join(HERE, f"backup-{int(time.time())}.json"), "w") as f:
            json.dump(cfg, f, indent=2)
        with open(os.path.join(HERE, "additions.json")) as f:
            merged = merge(cfg, json.load(f))
        if dry_run:
            print(json.dumps(merged, indent=2))
            return
        await client.app_client.update_robot_part(
            meta.machine_part_id, part.name,
            robot_config_json=json.dumps(merged),
            last_known_update=part.last_updated,
        )
        print("updated", part.name, {k: len(v) for k, v in merged.items() if isinstance(v, list)})
    finally:
        client.close()


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true")
    asyncio.run(main(p.parse_args().dry_run))
