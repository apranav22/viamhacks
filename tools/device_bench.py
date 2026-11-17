"""Benchmark OpenVINO models on every device of this machine (run ON the station, sorter venv).

    python tools/device_bench.py models/type_clf_v1/resnet18_avgpool.xml models/each_cardboard_v4/<top>.xml ...

Per model x device: compile time, p50/p90 latency of single synchronous inferences (LATENCY hint, f32 on GPU as the
anomaly runtime does), and whether the device compiled it at all. Prints one JSON line per result.
"""
import json
import sys
import time

import numpy as np
import openvino as ov


def bench(core, xml, device, n=50, warm=5):
    model = core.read_model(xml)
    shape = model.input(0).get_partial_shape()
    if not shape.is_static:
        model.reshape({model.input(0): [1, 3, 224, 224]})
    cfg = {"PERFORMANCE_HINT": "LATENCY", **({"INFERENCE_PRECISION_HINT": "f32"} if device != "NPU" else {})}
    t0 = time.perf_counter()
    compiled = core.compile_model(model, device, cfg)
    compile_ms = (time.perf_counter() - t0) * 1000
    req = compiled.create_infer_request()
    x = np.random.rand(*[d for d in compiled.input(0).shape]).astype(np.float32)
    for _ in range(warm):
        req.infer({0: x})
    ts = []
    for _ in range(n):
        t = time.perf_counter()
        req.infer({0: x})
        ts.append((time.perf_counter() - t) * 1000)
    return {"compile_ms": round(compile_ms), "p50_ms": round(float(np.percentile(ts, 50)), 2),
            "p90_ms": round(float(np.percentile(ts, 90)), 2), "input": list(compiled.input(0).shape)}


def main():
    core = ov.Core()
    for xml in sys.argv[1:]:
        for dev in core.available_devices:
            try:
                r = {"model": xml, "device": dev, "ok": True, **bench(core, xml, dev)}
            except Exception as e:  # noqa: BLE001  a device that cannot compile the model is a result too
                r = {"model": xml, "device": dev, "ok": False, "error": f"{type(e).__name__}: {str(e)[:160]}"}
            print(json.dumps(r), flush=True)


if __name__ == "__main__":
    main()
