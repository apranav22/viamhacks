"""Route for one item, drawn to scale from measured station coordinates (world mm, arm base = origin).

Measured: webcam lens (-40, -196, 25) looking +x; backboard (grey divider) face at x ~ 690; checkpoint
TCP (202, -166, 90) with the tool pointing back at the lens (250 mm, 15 deg up); table z -1.3.
Assumed (to confirm): box positions and sizes, pick zone.
"""

import math

LENS = (-40.0, -196.0, 25.0)
BACK_X = 690.0
CP = (202.0, -166.0, 90.0)
PART = (183.0, -168.0, 85.0)            # held part, ~20 mm past the TCP toward the lens
REJECT = (130.0, 290.0, -275.0, -115.0, 60.0)   # x0, x1, y0, y1, height (ASSUMED)
GOOD = (400.0, 560.0, -275.0, -115.0, 100.0)
PICK = (200.0, 470.0, 20.0, 280.0)
ITEM = (330.0, 150.0)
ELEV = math.radians(15)


def los_z(x):
    """Height of the webcam's line of sight through the held part at world x."""
    return LENS[2] + (x - LENS[0]) * math.tan(ELEV)


# ------------------------------------------------------------------ top view

def top_svg():
    s = 0.88
    X = lambda x: 40 + (x + 150) * s
    Y = lambda y: 30 + (330 - y) * s
    W = lambda d: d * s
    o = ['<svg viewBox="0 0 880 660" class="diagram" role="img" aria-label="top view of the route">',
         '<defs><marker id="ra" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
         '<path d="M0,0 L10,5 L0,10 z" fill="context-stroke"/></marker></defs>',
         f'<text x="16" y="20" class="small mute">MAP OF THE TABLE seen from above (a drawing angle, not a camera), to scale, world mm, arm base at 0,0. Arm → backboard is left → right.</text>']
    # grid
    for x in range(0, 701, 100):
        o.append(f'<line x1="{X(x)}" y1="{Y(320)}" x2="{X(x)}" y2="{Y(-340)}" stroke="#eef2f7"/>'
                 f'<text x="{X(x) + 2}" y="{Y(-340) + 14}" class="tiny mute">x {x}</text>')
    for y in range(-300, 301, 100):
        o.append(f'<line x1="{X(-130)}" y1="{Y(y)}" x2="{X(690)}" y2="{Y(y)}" stroke="#eef2f7"/>'
                 f'<text x="{X(-145)}" y="{Y(y) + 4}" class="tiny mute">y {y}</text>')
    # backboard
    o.append(f'<rect x="{X(BACK_X)}" y="{Y(320)}" width="{W(30)}" height="{W(660)}" fill="#94a3b8"/>'
             f'<text x="{X(BACK_X) - 6}" y="{Y(300)}" text-anchor="end" class="small dark">backboard (grey divider)</text>')
    # webcam view cone + line of sight
    lx, ly = X(LENS[0]), Y(LENS[1])
    for sgn in (1, -1):
        a = math.radians(28) * sgn
        ye = max(-345.0, min(320.0, LENS[1] + (BACK_X - LENS[0]) * math.tan(a)))
        xe = LENS[0] + (ye - LENS[1]) / math.tan(a)
        o.append(f'<line x1="{lx}" y1="{ly}" x2="{X(min(xe, BACK_X))}" y2="{Y(ye)}" stroke="#a855f7" stroke-opacity=".35"/>')
    o.append(f'<line x1="{lx}" y1="{ly}" x2="{X(BACK_X)}" y2="{ly}" stroke="#a855f7" stroke-width="1.5" stroke-dasharray="6 5"/>')
    # boxes
    for (x0, x1, y0, y1, h), col, fill, name in ((REJECT, "#dc2626", "#fee2e2", "1. REJECT box (nearest)"),
                                                   (GOOD, "#16a34a", "#dcfce7", "2. GOOD box (further)")):
        o.append(f'<rect x="{X(x0)}" y="{Y(y1)}" width="{W(x1 - x0)}" height="{W(y1 - y0)}" rx="6" fill="{fill}" stroke="{col}" stroke-width="2"/>'
                 f'<text x="{X((x0 + x1) / 2)}" y="{Y(y0) + 16}" text-anchor="middle" class="small dark">{name}</text>')
    # arm base + webcam
    o.append(f'<circle cx="{X(0)}" cy="{Y(0)}" r="{W(75)}" fill="#e2e8f0" stroke="#475569" stroke-width="2"/>'
             f'<text x="{X(0)}" y="{Y(0) + 4}" text-anchor="middle" class="small dark">arm base</text>')
    o.append(f'<rect x="{X(-116)}" y="{Y(-156)}" width="{W(97)}" height="{W(80)}" rx="4" fill="#7c3aed"/>'
             f'<text x="{X(-68)}" y="{Y(-236) + 16}" text-anchor="middle" class="small dark">webcam</text>')
    # pick zone + item
    x0, x1, y0, y1 = PICK
    o.append(f'<rect x="{X(x0)}" y="{Y(y1)}" width="{W(x1 - x0)}" height="{W(y1 - y0)}" rx="8" fill="#f8fafc" stroke="#64748b" stroke-width="2" stroke-dasharray="7 5"/>'
             f'<text x="{X((x0 + x1) / 2)}" y="{Y(y1) - 6}" text-anchor="middle" class="small dark">pick zone: judge places ONE item</text>')
    ix, iy = ITEM
    o.append(f'<rect x="{X(ix) - 18}" y="{Y(iy) - 5}" width="36" height="10" rx="3" fill="#38bdf8" transform="rotate(-30 {X(ix)} {Y(iy)})"/>')
    # route
    cx, cy = X(CP[0]), Y(CP[1])
    o.append(f'<path d="M{X(ix)},{Y(iy) + 14} C{X(ix) - 20},{Y(40)} {cx + 40},{cy - 70} {cx + 4},{cy - 12}" fill="none" stroke="#2563eb" stroke-width="3.5" marker-end="url(#ra)"/>')
    o.append(f'<circle cx="{cx}" cy="{cy}" r="11" fill="#fef3c7" stroke="#f59e0b" stroke-width="3"/>'
             f'<text x="{cx}" y="{cy + 4}" text-anchor="middle" class="tiny dark">CP</text>')
    gx = X((GOOD[0] + GOOD[1]) / 2)
    o.append(f'<path d="M{cx + 14},{cy} L{gx - 8},{cy}" fill="none" stroke="#16a34a" stroke-width="3.5" stroke-dasharray="9 5" marker-end="url(#ra)"/>'
             f'<circle cx="{gx}" cy="{cy}" r="7" fill="#16a34a"/>')
    o.append(f'<path d="M{cx},{cy + 13} L{cx},{cy + 42}" stroke="#dc2626" stroke-width="3.5" marker-end="url(#ra)"/>')
    # labels
    lab = [(X(ix) + 26, Y(iy) - 10, "① hover + wrist look (top face) → first motion"),
           (X(ix) - 120, Y(60), "② pick, lift"),
           (X(120), Y(-55), "③ checkpoint (CP) ABOVE the reject box"),
           (X(120), Y(-55) + 15, "    part faces the webcam → bottom face"),
           (cx - 120, cy + 58, "④a defect → open here (drop)"),
           (X(400), Y(-100), "④b good → carry on, drop")]
    for x, y, t in lab:
        o.append(f'<text x="{x}" y="{y}" class="small" font-weight="600" fill="#0f172a">{t}</text>')
    o.append(f'<text x="{X(300)}" y="{Y(-196) + 4}" class="tiny" fill="#7c3aed">webcam line of sight</text>')
    o.append('</svg>')
    return "\n".join(o)


# ------------------------------------------------------------------ side view

def side_svg():
    s = 0.88
    X = lambda x: 40 + (x + 150) * s
    Z = lambda z: 285 - z * s
    o = ['<svg viewBox="0 0 880 320" class="diagram" role="img" aria-label="cross-section along the webcam line">',
         '<text x="16" y="20" class="small mute">CROSS-SECTION through the webcam line (a drawing angle, not a camera), to scale. Up = z.</text>']
    o.append(f'<line x1="{X(-150)}" y1="{Z(0)}" x2="{X(720)}" y2="{Z(0)}" stroke="#475569" stroke-width="2"/>'
             f'<text x="{X(-140)}" y="{Z(0) + 16}" class="tiny mute">table</text>')
    o.append(f'<rect x="{X(BACK_X)}" y="{Z(300)}" width="{30 * s}" height="{300 * s}" fill="#94a3b8"/>'
             f'<text x="{X(BACK_X) - 6}" y="{Z(270)}" text-anchor="end" class="small dark">backboard</text>')
    for (x0, x1, _, _, h), col, fill, name in ((REJECT, "#dc2626", "#fee2e2", "reject"), (GOOD, "#16a34a", "#dcfce7", "good")):
        o.append(f'<path d="M{X(x0)},{Z(h)} L{X(x0)},{Z(0)} L{X(x1)},{Z(0)} L{X(x1)},{Z(h)}" fill="{fill}" stroke="{col}" stroke-width="2.5"/>'
                 f'<text x="{X((x0 + x1) / 2)}" y="{Z(0) - 8}" text-anchor="middle" class="small dark">{name} box (h {h:.0f}? assumed)</text>')
    o.append(f'<line x1="{X(LENS[0])}" y1="{Z(LENS[2])}" x2="{X(BACK_X)}" y2="{Z(los_z(BACK_X))}" stroke="#a855f7" stroke-width="2" stroke-dasharray="6 5"/>'
             f'<text x="{X(600)}" y="{Z(los_z(600)) + 16}" text-anchor="middle" class="tiny" fill="#7c3aed">webcam line of sight (15° up)</text>')
    o.append(f'<rect x="{X(-100)}" y="{Z(55)}" width="{75 * s}" height="{55 * s}" rx="4" fill="#7c3aed"/>'
             f'<text x="{X(-62)}" y="{Z(0) + 16}" text-anchor="middle" class="small dark">webcam</text>')
    ux, uz = -math.cos(ELEV), -math.sin(ELEV)          # tool axis, toward the lens
    nx, nz = -uz, ux
    fx, fz = CP[0] - ux * 150, CP[2] - uz * 150          # flange, 150 mm behind the TCP
    def quad(ax, az, bx, bz, w):
        pts = [(ax + nx * w, az + nz * w), (bx + nx * w, bz + nz * w), (bx - nx * w, bz - nz * w), (ax - nx * w, az - nz * w)]
        return " ".join(f"{X(x):.1f},{Z(z):.1f}" for x, z in pts)
    o.append(f'<polygon points="{quad(fx, fz, CP[0], CP[2], 34)}" fill="#e2e8f0" stroke="#475569" stroke-width="2"/>'
             f'<text x="{X((fx + CP[0]) / 2)}" y="{Z((fz + CP[2]) / 2) + 4}" text-anchor="middle" class="small dark">gripper</text>')
    for w in (14, -14):
        ax, az = CP[0] + nx * w, CP[2] + nz * w
        o.append(f'<line x1="{X(ax):.1f}" y1="{Z(az):.1f}" x2="{X(ax + ux * 24):.1f}" y2="{Z(az + uz * 24):.1f}" stroke="#111827" stroke-width="6"/>')
    o.append(f'<rect x="{X(PART[0]) - 9}" y="{Z(PART[2]) - 6}" width="18" height="12" rx="3" fill="#38bdf8" stroke="#0369a1"/>'
             f'<text x="{X(PART[0]) - 14}" y="{Z(PART[2]) - 26}" text-anchor="end" class="tiny" fill="#0369a1">held part, bottom face → webcam</text>')
    wx, wz = fx + nx * 40, fz + nz * 40
    o.append(f'<rect x="{X(wx) - 12:.1f}" y="{Z(wz) - 6:.1f}" width="24" height="12" rx="3" fill="#0f172a"/>'
             f'<text x="{X(wx) + 16:.1f}" y="{Z(wz) + 4:.1f}" class="tiny dark">wrist cam (faces the webcam)</text>')
    zx = los_z(REJECT[0])
    o.append(f'<line x1="{X(REJECT[0]) - 4}" y1="{Z(zx)}" x2="{X(REJECT[0]) + 30}" y2="{Z(zx)}" stroke="#dc2626" stroke-width="2"/>'
             f'<text x="{X(REJECT[0]) - 8}" y="{Z(zx) + 4}" text-anchor="end" class="tiny" fill="#b91c1c">reject near wall must stay below ≈{zx:.0f} mm</text>')
    o.append(f'<text x="{X(-130)}" y="{Z(215)}" class="small" font-weight="600" fill="#0f172a">③ checkpoint: TCP (202, −166, 90), 250 mm from the lens</text>')
    o.append('</svg>')
    return "\n".join(o)

def opposed_svg():
    """The key idea: the wrist cam and the webcam look at the part from exactly opposite sides."""
    G, B = "#16a34a", "#2563eb"
    def part(cx, cy, top_dir):
        # circle = bolt cross-section; half facing top_dir is the TOP face (green), other half BOTTOM (blue)
        a0 = {"up": 180, "right": 90}[top_dir]
        def arc(a1, a2, col):
            import math as m
            p1 = (cx + 16 * m.cos(m.radians(a1)), cy - 16 * m.sin(m.radians(a1)))
            p2 = (cx + 16 * m.cos(m.radians(a2)), cy - 16 * m.sin(m.radians(a2)))
            return f'<path d="M{p1[0]:.1f},{p1[1]:.1f} A16,16 0 0 1 {p2[0]:.1f},{p2[1]:.1f}" fill="none" stroke="{col}" stroke-width="7"/>'
        return (f'<circle cx="{cx}" cy="{cy}" r="16" fill="#cbd5e1"/>' + arc(a0, a0 - 180, G) + arc(a0 - 180, a0 - 360, B))
    o = ['<svg viewBox="0 0 900 345" class="diagram" role="img" aria-label="opposed views">',
         '<defs><marker id="oa" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="context-stroke"/></marker></defs>',
         '<text x="16" y="22" class="small" font-weight="700" fill="#0f172a">OPPOSED VIEWS (bolt cross-section)</text>',
         f'<g font-size="12"><rect x="560" y="10" width="12" height="12" fill="{G}"/><text x="578" y="21" class="small">top face (wrist cam sees it)</text>'
         f'<rect x="740" y="10" width="12" height="12" fill="{B}"/><text x="758" y="21" class="small">bottom face (webcam)</text></g>',
         # left panel: hover
         '<text x="20" y="52" class="small" font-weight="600">1. HOVER, before the grasp</text>',
         '<line x1="20" y1="262" x2="360" y2="262" stroke="#475569" stroke-width="3"/><text x="24" y="280" class="tiny mute">table</text>',
         part(190, 246, "up"),
         '<rect x="160" y="62" width="60" height="22" rx="4" fill="#0f172a"/><text x="230" y="78" class="small">wrist cam</text>',
         f'<line x1="190" y1="88" x2="190" y2="222" stroke="{G}" stroke-width="3" marker-end="url(#oa)"/>',
         '<text x="200" y="160" class="small">looks DOWN: top face</text>',
         f'<text x="40" y="306" class="small" fill="{B}">bottom face hidden against the table</text>',
         '<path d="M370,170 C395,150 405,150 430,170" fill="none" stroke="#94a3b8" stroke-width="2" marker-end="url(#oa)"/>'
         '<text x="400" y="140" text-anchor="middle" class="tiny mute">grab, lift,</text><text x="400" y="153" text-anchor="middle" class="tiny mute">move ~1.5 s</text>',
         # right panel: checkpoint
         '<text x="450" y="52" class="small" font-weight="600">2. CHECKPOINT above the reject box (one stop, ~0.3 s still)</text>',
         '<rect x="452" y="150" width="46" height="34" rx="5" fill="#7c3aed"/><text x="452" y="204" class="small">webcam</text>',
         part(596, 167, "right"),
         '<line x1="642" y1="147" x2="586" y2="147" stroke="#111827" stroke-width="6"/><line x1="642" y1="187" x2="586" y2="187" stroke="#111827" stroke-width="6"/>',
         '<rect x="642" y="130" width="120" height="74" rx="8" fill="#e2e8f0" stroke="#475569" stroke-width="2"/><text x="668" y="172" class="small dark">gripper</text>',
         '<rect x="740" y="98" width="48" height="20" rx="4" fill="#0f172a"/><text x="794" y="112" class="tiny dark">wrist cam</text>',
         '<line x1="738" y1="108" x2="520" y2="108" stroke="#0f172a" stroke-width="2" stroke-dasharray="6 4" marker-end="url(#oa)"/>',
         '<text x="530" y="100" class="tiny dark">wrist cam faces the webcam (top image already taken)</text>',
         f'<line x1="500" y1="167" x2="574" y2="167" stroke="{B}" stroke-width="3" marker-end="url(#oa)"/>',
         '<text x="506" y="232" class="small">webcam looks at the bottom face</text>',
         '<rect x="860" y="60" width="22" height="210" fill="#94a3b8"/><text x="852" y="290" text-anchor="end" class="tiny dark">backboard</text>',
         '<line x1="500" y1="250" x2="848" y2="250" stroke="#a855f7" stroke-width="1.5" stroke-dasharray="5 4"/>',
         '<text x="506" y="266" class="tiny" fill="#7c3aed">webcam line of sight → gripper → backboard (clean background)</text>',
         '<text x="20" y="334" class="small" font-weight="600" fill="#0f172a">In the part&#39;s own frame the two view directions differ by exactly 180°, for any grasp angle.</text>',
         '</svg>']
    return "\n".join(o)


def section():
    steps = [
        ("WATCH", "home pose; wrist cam sees the item land, hand gone"),
        ("① HOVER + LOOK", "first motion (latency stops). Wrist close-up of the TOP face → initial guess"),
        ("② PICK", "descend, grab across the shank, verify holding, lift"),
        ("③ CHECKPOINT", "above the reject box: part pointed at the webcam, 0.3 s still → BOTTOM face (+ side tilt)"),
        ("DECIDE", "top + bottom vs the canonical good part (anomaly model) + tape check → log line"),
        ("④a DEFECT", "open right here: it falls into the reject box"),
        ("④b GOOD", "keep going +x, lower into the good box, open"),
        ("HOME", "back to watch"),
    ]
    flow = "".join(f'<div class="step{" mark" if "HOVER" in n else " mark2" if "CHECK" in n else ""}"><b>{n}</b><span>{d}</span></div>'
                   + ('<div class="arrow">→</div>' if i < len(steps) - 1 else "") for i, (n, d) in enumerate(steps))
    t = [("watch → hover", "1.4"), ("look + aim", "0.9"), ("descend + grab + lift", "2.4"), ("lift → checkpoint", "≈1.5"),
         ("still + capture + score", "0.4"), ("defect: open", "0.8"), ("good: → box, lower, open", "≈2.3"), ("→ home", "1.2")]
    times = "".join(f"<tr><td>{a}</td><td>{b} s</td></tr>" for a, b in t)
    return f"""<section id="route"><h2>The route for one item</h2>
<p class="lead">How I read the plan: both boxes sit on the line from the arm to the backboard, <b>reject first, good second</b>.
The check happens <b>in the air directly above the reject box</b>, with the webcam looking past the part at the backboard.
A defect is dropped right there (shortest path). Only a part that passes travels on to the good box. The reject path is a strict
prefix of the good path, so a defect never costs extra motion.</p>
<div class="flow">{flow}</div>
{opposed_svg()}
{top_svg()}
{side_svg()}
<div class="grid g3" style="margin-top:16px">
<div class="card"><h3>Why it's diametrically opposed by construction</h3>The wrist cam looks along the gripper's axis. At the hover that axis points
down, so it images the <b>top</b>. The grasp keeps the part fixed in the fingers, and at the checkpoint the same axis points <b>at the webcam</b>,
so the webcam looks back along it: the <b>bottom</b>. Opposite faces, one stop, no searching. Only the band under the finger pads is grazing
in both; one optional tilt at the same stop covers it.</div>
<div class="card"><h3>Why each camera faces where it does</h3><ul>
<li><b>Webcam: no depth</b> (plain <code>rdk:builtin:webcam</code>, 640×480). It can only separate the part from the background by looks, so it faces the plain <b>backboard</b>.</li>
<li><b>Wrist RealSense: has depth.</b> It doesn't need a clean background: keep only pixels within a set distance of the part (or above the table) and the busy scene behind is cut off.</li>
<li>So the busy side of the room is always behind the depth camera's subject, and the plain side is always behind the webcam's subject.</li></ul></div>
<div class="card"><h3>Constraints this layout creates</h3><ul>
<li>The reject box sits <b>under the webcam's line of sight</b>. Its near wall must be lower than ≈{los_z(REJECT[0]):.0f} mm or it hides the part. A low tray works; a tall box needs the checkpoint raised</li>
<li>The good box sits behind the part in the image only below ~{los_z(GOOD[0]):.0f} mm: boxes under ~14 cm stay out of the background</li>
<li>Keep the laptop off the area left of the webcam (blocks a side view)</li></ul></div>
<div class="card"><h3>Time per item (measured moves)</h3><table>{times}</table>
<p class="kv" style="margin-top:6px">≈ 11 s for a defect, ≈ 13 s for a good part. Six items ≈ 75 s of our time.</p></div>
</div>
<p class="lead" style="margin-top:10px"><b>Measured:</b> webcam lens, backboard, checkpoint pose (reached live), table height. <b>Assumed:</b> box positions and sizes (drawn
15 × 16 cm, reject 6 cm tall, good 10 cm), pick zone. Tell me where the boxes actually go and I'll redraw and re-plan the checkpoint over the reject box.</p>
</section>"""
