"""[codex/unknown · op Ali · Mac.mynetworksettings.com · ali/judges-presentation · 2026-11-14]
Package the built presentation with static-server instructions; no network or robot access.
"""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parent
DIST = ROOT / "dist"
if not (DIST / "index.html").is_file():
    raise SystemExit("Run npm run build first")

with ZipFile(ROOT / "judges-presentation.zip", "w", ZIP_DEFLATED) as archive:
    for path in sorted(DIST.rglob("*")):
        if path.is_file():
            archive.write(path, path.relative_to(DIST))
    archive.writestr("README.txt", """[codex/unknown · op Ali · Mac.mynetworksettings.com · ali/judges-presentation · 2026-11-14]

Spot it, sort it — Viam x Intel judges presentation

Unzip this folder. Open a terminal here and run:
  python3 -m http.server 5199 --bind 127.0.0.1
Then open http://127.0.0.1:5199 in your browser.
No npm, robot access or internet connection is needed to present.
Do not open index.html directly using file://.

Arrow keys / Space: advance. Click left quarter: back. F: fullscreen.
N: speaker notes. G: choose step. Sources: provenance and caveats.
Presenter opens synchronized previews, notes and a timer in another window
of the same browser profile. Put the audience window on the projector.

14 steps, with a five-minute talk track. Saved captures and original log
results are distinct from offline CPU replay. The candidate was not activated.
Repeated physical specimens mean these are development results, not
independent-specimen accuracy or judge-set results. No robot connection.

Use the Sources panel and evidence.json for source paths, image hashes,
reconstruction details, candidate identity, event references and limits.
""")
print(ROOT / "judges-presentation.zip")
