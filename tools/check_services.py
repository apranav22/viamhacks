"""Wait for the Track 3 services to come up, then report devices, latency and a test score. Moves nothing."""

import asyncio
import time

from viam.services.generic import Generic
from viam.services.vision import Vision

from vh.scan import classify
from station import connect

WANTED = ("ov-anomaly", "ov-diag", "anomaly")


async def main(timeout_s=300):
    deadline = time.time() + timeout_s
    while True:
        async with await connect() as machine:
            st = await machine.get_machine_status()
            states = {r.name.name: (r.state, r.error) for r in st.resources if r.name.name in WANTED}
            print(time.strftime("%H:%M:%S"), {k: (s, e[:200]) for k, (s, e) in states.items()})
            ready = len(states) == len(WANTED) and all(s == 3 and not e for s, e in states.values())
            if ready:
                diag = Generic.from_robot(machine, "ov-diag")
                print("devices:", await diag.do_command({"command": "list_devices"}))
                print("compiled:", await diag.do_command({"command": "get_compiled_properties"}))
                print("benchmark:", await diag.do_command({"command": "benchmark", "iterations": 50}))
                score, boxes = await classify(Vision.from_robot(machine, "anomaly"))
                print(f"anomaly score on the current view: {score:.3f}, {boxes} anomaly boxes")
                return
        if time.time() > deadline:
            raise SystemExit("services not ready; check the LOGS tab for the modules")
        await asyncio.sleep(15)


if __name__ == "__main__":
    asyncio.run(main())
