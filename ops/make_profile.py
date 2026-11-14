"""Write the Stream Deck profile (ops/streamdeck/Viam Ops.streamDeckProfile) and fallback .cmd wrappers.

    ..\\.venv\\Scripts\\python.exe ops\\make_profile.py --console http://100.104.1.88:8790 --model 20GBD9901

Layout: 15-key Stream Deck (5 x 3), key ids "col,row". See ops/STREAMDECK.md.
"""
import argparse
import io
import json
import uuid
import zipfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
OUT = HERE / "streamdeck"
BOARD = "https://claude.ai/artifact/KtWjxBh8gvDxA9N8oaevhh"
STATION_DASH = "http://172.16.0.182:8775"
RED, ORANGE, GREEN, BLUE, GRAY, PURPLE = "#c62828", "#ef8f00", "#2e7d32", "#1f5fbf", "#37404d", "#5b3c99"

# Windows virtual-key + Qt key codes for the arrow keys (Stream Deck hotkey action)
ARROWS = {"Left": (37, 16777234), "Right": (39, 16777236)}


def keys(c):
    g = lambda p: ("get", f"{c}{p}")        # noqa: E731  background GET
    o = lambda u: ("open", u)               # noqa: E731  open in the default browser
    return {
        (0, 0): ("STOP", RED, g("/api/stop")),
        (1, 0): ("ARM\nJUDGED\nCPU", ORANGE, g("/api/arm?preset=judged")),
        (2, 0): ("CONFIRM\nSTART\nE-stop\nmanned?", GREEN, g("/api/confirm")),
        (3, 0): ("ARM\nJUDGED\nNPU", ORANGE, g("/api/arm?preset=judged_npu")),
        (4, 0): ("OPS\nCONSOLE", BLUE, o(f"{c}/")),
        (0, 1): ("ARM\nCOLLECT\nm16", ORANGE, g("/api/arm?preset=collect_socket_m16")),
        (1, 1): ("ARM\nCOLLECT\nhexbolt", ORANGE, g("/api/arm?preset=collect_hex_bolt_short")),
        (2, 1): ("STATUS", GRAY, o(f"{c}/api/status")),
        (3, 1): ("WEBCAM\nSNAP", GRAY, o(f"{c}/api/snapshot?cam=overview-cam")),
        (4, 1): ("WRIST\nSNAP", GRAY, o(f"{c}/api/snapshot?cam=cam")),
        (0, 2): ("PREV\nSLIDE", PURPLE, ("hotkey", "Left")),
        (1, 2): ("NEXT\nSLIDE", PURPLE, ("hotkey", "Right")),
        (2, 2): ("LIVE\nBOARD", BLUE, o(BOARD)),
        (3, 2): ("STATION\nDASH\n(LAN)", BLUE, o(STATION_DASH)),
        (4, 2): ("DECISIONS", GRAY, o(f"{c}/api/decisions")),
    }


def icon(text, color):
    im = Image.new("RGB", (144, 144), color)
    d = ImageDraw.Draw(im)
    lines = text.split("\n")
    size = 34 if len(lines) == 1 and len(text) <= 6 else 24
    try:
        font = ImageFont.truetype("arialbd.ttf", size)
    except OSError:
        font = ImageFont.load_default()
    h = size + 4
    y = (144 - h * len(lines)) // 2
    for ln in lines:
        w = d.textlength(ln, font=font)
        d.text(((144 - w) / 2, y), ln, fill="white", font=font)
        y += h
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()


def action(kind, arg, img):
    state = {"Image": img, "Title": "", "ShowTitle": False}
    if kind == "get":
        return {"Name": "Website", "UUID": "com.elgato.streamdeck.system.website", "State": 0, "States": [state],
                "Settings": {"openInBrowser": False, "path": arg}}
    if kind == "open":
        return {"Name": "Website", "UUID": "com.elgato.streamdeck.system.website", "State": 0, "States": [state],
                "Settings": {"openInBrowser": True, "path": arg}}
    vk, qt = ARROWS[arg]
    hk = {"KeyCmd": False, "KeyCtrl": False, "KeyModifiers": 0, "KeyOption": False, "KeyShift": False,
          "NativeCode": vk, "QTKeyCode": qt, "VKeyCode": vk}
    none = {"KeyCmd": False, "KeyCtrl": False, "KeyModifiers": 0, "KeyOption": False, "KeyShift": False,
            "NativeCode": 146, "QTKeyCode": 33554431, "VKeyCode": -1}
    return {"Name": "Hotkey", "UUID": "com.elgato.streamdeck.system.hotkey", "State": 0, "States": [state],
            "Settings": {"Coalesce": True, "Hotkeys": [hk, none, none, none]}}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--console", default="http://100.104.1.88:8790", help="ops console base URL as the deck's PC sees it")
    ap.add_argument("--model", default="20GBD9901", help="Stream Deck model id (sticker / app: 15-key)")
    a = ap.parse_args()
    OUT.mkdir(exist_ok=True)
    pid = str(uuid.uuid5(uuid.NAMESPACE_URL, "viam-ops-" + a.console)).upper()
    folder = f"{pid}.sdProfile"
    actions, files = {}, {}
    for (col, row), (title, color, (kind, arg)) in keys(a.console).items():
        img = f"Images/{col}_{row}.png"
        files[f"{folder}/{img}"] = icon(title, color)
        actions[f"{col},{row}"] = action(kind, arg, img)
    manifest = {"Actions": actions, "DeviceModel": a.model, "DeviceUUID": "", "Name": "Viam Ops", "Version": "1.0"}
    path = OUT / "Viam Ops.streamDeckProfile"
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(f"{folder}/manifest.json", json.dumps(manifest, indent=1))
        for name, data in files.items():
            z.writestr(name, data)
    # Fallback: one .cmd per GET key, for the Stream Deck "Open" (System > Open) action or a double-click
    for (col, row), (title, color, (kind, arg)) in keys(a.console).items():
        if kind != "get":
            continue
        name = arg.rsplit("/", 1)[1].replace("?preset=", "_")       # stop, confirm, arm_judged, arm_judged_npu, ...
        (OUT / f"{name}.cmd").write_text(f'@curl.exe -s -m 30 "{arg}"\r\n@timeout /t 2 >nul\r\n', encoding="ascii")
    (OUT / "preview.png").write_bytes(preview(a.console))
    print("wrote", path, "and", len(list(OUT.glob('*.cmd'))), ".cmd wrappers")


def preview(c):
    sheet = Image.new("RGB", (5 * 154 + 10, 3 * 154 + 10), "#111")
    for (col, row), (title, color, _) in keys(c).items():
        sheet.paste(Image.open(io.BytesIO(icon(title, color))), (10 + col * 154, 10 + row * 154))
    buf = io.BytesIO()
    sheet.save(buf, "PNG")
    return buf.getvalue()


if __name__ == "__main__":
    main()
