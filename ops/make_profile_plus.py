"""Install the "Viam Demo" profile on a Stream Deck + (8 keys, 4 dials) on this Mac, driving ops/console.py.

    python ops/make_profile_plus.py                   # console at http://127.0.0.1:8790, restarts the Stream Deck app
    python ops/make_profile_plus.py --no-restart      # write only

Writes straight into ~/Library/Application Support/com.elgato.StreamDeck/ProfilesV3 (the app reads that folder on
start, so it is quit first and reopened). Re-running replaces the same profile; other profiles are untouched.
Layout (key ids "col,row"), see ops/STREAMDECK.md:

    row 0   STOP          START DEMO   COLLECT DEMO    OPS CONSOLE
    row 1   WEBCAM SNAP   WRIST SNAP   DECISIONS       STATION DASH
    dial 0  turn: previous / next slide (arrow keys to the focused window)
"""
import argparse
import io
import json
import shutil
import subprocess
import time
import uuid
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path.home() / "Library/Application Support/com.elgato.StreamDeck/ProfilesV3"
STATION_DASH = "http://172.16.0.182:8775"
MODEL = "20GBD9901"                    # Stream Deck +
RED, ORANGE, GREEN, BLUE, GRAY = "#c62828", "#ef8f00", "#2e7d32", "#1f5fbf", "#37404d"
FONT = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
# macOS key codes for the arrow keys (NativeCode / Qt key code)
ARROWS = {"Left": (123, 16777234), "Right": (124, 16777236)}
NO_KEY = {"KeyCmd": False, "KeyCtrl": False, "KeyModifiers": 0, "KeyOption": False, "KeyShift": False,
          "NativeCode": -1, "QTKeyCode": 33554431, "VKeyCode": -1}


def keys(c):
    g = lambda p: ("get", f"{c}{p}")        # noqa: E731  background GET
    o = lambda u: ("open", u)               # noqa: E731  open in the default browser
    return {
        (0, 0): ("STOP", RED, g("/api/stop_now")),
        (1, 0): ("START\nDEMO", GREEN, g("/api/go?preset=demo")),
        (2, 0): ("COLLECT\nDEMO", ORANGE, g("/api/go?preset=collect_demo")),
        (3, 0): ("OPS\nCONSOLE", BLUE, o(f"{c}/")),
        (0, 1): ("WEBCAM\nSNAP", GRAY, o(f"{c}/api/snapshot?cam=overview-cam")),
        (1, 1): ("WRIST\nSNAP", GRAY, o(f"{c}/api/snapshot?cam=cam")),
        (2, 1): ("DECISIONS", GRAY, o(f"{c}/api/decisions")),
        (3, 1): ("STATION\nDASH", BLUE, o(STATION_DASH)),
    }


def icon(text, color, size=(144, 144)):
    im = Image.new("RGB", size, color)
    d = ImageDraw.Draw(im)
    lines = text.split("\n")
    fs = 34 if len(lines) == 1 and len(text) <= 6 else 24
    try:
        font = ImageFont.truetype(FONT, fs)
    except OSError:
        font = ImageFont.load_default()
    h = fs + 4
    y = (size[1] - h * len(lines)) // 2
    for ln in lines:
        d.text(((size[0] - d.textlength(ln, font=font)) / 2, y), ln, fill="white", font=font)
        y += h
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()


def key_action(kind, arg, img):
    return {"ActionID": str(uuid.uuid4()), "LinkedTitle": True, "Name": "Website", "Resources": None,
            "Settings": {"openInBrowser": kind == "open", "path": arg}, "State": 0,
            "States": [{"Image": img, "ShowTitle": False, "Title": ""}],
            "UUID": "com.elgato.streamdeck.system.website"}


def slide_dial(img):
    def hk(name):
        native, qt = ARROWS[name]
        return {**NO_KEY, "NativeCode": native, "QTKeyCode": qt, "VKeyCode": native}
    # Hotkeys: [turn left, turn right, press, touch]
    return {"ActionID": str(uuid.uuid4()), "Encoder": {"Icon": img}, "LinkedTitle": True, "Name": "Hotkey",
            "Plugin": {"Name": "Activate a Key Command", "UUID": "com.elgato.streamdeck.system.hotkey", "Version": "1.0"},
            "Resources": None, "Settings": {"Coalesce": True, "Hotkeys": [hk("Left"), hk("Right"), NO_KEY, NO_KEY]},
            "State": 0, "States": [{"Title": "Slides"}], "UUID": "com.elgato.streamdeck.system.hotkey"}


def device_uuid():
    """The connected deck's id, taken from an existing profile for this model (the app wrote it)."""
    for m in ROOT.glob("*.sdProfile/manifest.json"):
        dev = json.loads(m.read_text()).get("Device", {})
        if dev.get("Model") == MODEL and dev.get("UUID"):
            return dev["UUID"]
    return ""


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--console", default="http://127.0.0.1:8790", help="ops console base URL as this Mac sees it")
    ap.add_argument("--no-restart", action="store_true", help="do not quit and reopen the Stream Deck app")
    a = ap.parse_args()
    pid = str(uuid.uuid5(uuid.NAMESPACE_URL, "viam-demo-plus-" + a.console)).upper()
    page = str(uuid.uuid5(uuid.NAMESPACE_URL, "viam-demo-plus-page-" + a.console)).upper()
    blank = str(uuid.uuid5(uuid.NAMESPACE_URL, "viam-demo-plus-blank-" + a.console)).upper()
    if not a.no_restart:
        subprocess.run(["pkill", "-f", "Elgato Stream Deck.app/Contents/MacOS"], check=False)
        time.sleep(3)
    prof = ROOT / f"{pid}.sdProfile"
    shutil.rmtree(prof, ignore_errors=True)
    pdir = prof / "Profiles" / page
    (pdir / "Images").mkdir(parents=True)
    (prof / "Profiles" / blank).mkdir(parents=True)
    (prof / "Images").mkdir()
    actions = {}
    for (col, row), (title, color, (kind, arg)) in keys(a.console).items():
        img = f"Images/key_{col}_{row}.png"
        (pdir / img).write_bytes(icon(title, color))
        actions[f"{col},{row}"] = key_action(kind, arg, img)
    (pdir / "Images/dial_slides.png").write_bytes(icon("SLIDES", "#5b3c99"))
    enc = {"0,0": slide_dial("Images/dial_slides.png")}
    (pdir / "manifest.json").write_text(json.dumps({"Controllers": [
        {"Actions": actions, "Type": "Keypad"}, {"Actions": enc, "Type": "Encoder"}], "Icon": "", "Name": ""}))
    (prof / "Profiles" / blank / "manifest.json").write_text(json.dumps({"Controllers": [
        {"Actions": None, "Type": "Keypad"}, {"Actions": None, "Type": "Encoder"}], "Icon": "", "Name": ""}))
    (prof / "manifest.json").write_text(json.dumps({
        "Device": {"Model": MODEL, "UUID": device_uuid()}, "Name": "Viam Demo",
        "Pages": {"Current": page.lower(), "Default": blank.lower(), "Pages": [page.lower()]}, "Version": "3.0"}))
    print("wrote", prof)
    if not a.no_restart:
        subprocess.run(["open", "-a", "Elgato Stream Deck"], check=False)
        print('reopened the Stream Deck app: pick profile "Viam Demo" for the Stream Deck + if it is not active')


if __name__ == "__main__":
    main()
