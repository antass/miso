"""Books that aren't reflowable text.

* Glyph books — text drawn as SVG outlines (no real text): render each page in headless Chrome,
  OCR it with macOS Vision (ocr.swift), and rebuild reading order from the line boxes.
* Fixed-layout books — every line (or word) is absolutely positioned: rebuild lines, then join
  lines back into paragraphs so the normal recipe extractor can read them.
"""
import concurrent.futures
import hashlib
import json
import os
import posixpath
import re
import shutil
import statistics
import subprocess
import tempfile

import extract

CACHE = os.path.expanduser("~/Library/Application Support/Miso")
OCR_BIN = os.path.join(CACHE, "bin", "ocr")
OCR_SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ocr.swift")
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"


def available():
    if not os.path.exists(CHROME):
        return False
    if not os.path.exists(OCR_BIN) or os.path.getmtime(OCR_BIN) < os.path.getmtime(OCR_SRC):
        os.makedirs(os.path.dirname(OCR_BIN), exist_ok=True)
        r = subprocess.run(["swiftc", "-O", OCR_SRC, "-o", OCR_BIN], capture_output=True, timeout=600)
        if r.returncode:
            return False
    return True


# ------------------------------------------------------------------ OCR of glyph books

def _page_size(html):
    m = re.search(r'<svg[^>]*\bwidth="([\d.]+)"[^>]*\bheight="([\d.]+)"', html) or \
        re.search(r'viewbox="0 0 ([\d.]+) ([\d.]+)"', html, re.I)
    return (int(float(m.group(1))), int(float(m.group(2)))) if m else (900, 1200)


def _render(args):
    chrome_dir, html_path, png, w, h = args
    try:
        subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars",
                        "--no-first-run", "--no-default-browser-check", "--force-device-scale-factor=2",
                        f"--window-size={w},{h}", f"--screenshot={png}", "file://" + html_path],
                       capture_output=True, timeout=60)
    except subprocess.TimeoutExpired:
        pass
    return png


def ocr_book(ep, progress=None):
    """Return line blocks for a glyph-drawn book (cached by file signature)."""
    st = os.stat(ep.path)
    key = hashlib.sha1(f"{ep.path}|{st.st_size}|{int(st.st_mtime)}|v3".encode()).hexdigest()
    cache = os.path.join(CACHE, "ocr", key + ".json")
    if os.path.exists(cache):
        with open(cache) as f:
            return json.load(f)
    if not available():
        return []
    tmp = tempfile.mkdtemp(prefix="miso-ocr-")
    try:
        jobs = []
        for di, doc in enumerate(ep.spine):
            html = ep.read(doc)
            for src in set(re.findall(r'(?:src|href)="([^"#:]+\.(?:jpe?g|png|gif|webp|svg|css))"', html, re.I)):
                full = posixpath.normpath(posixpath.join(posixpath.dirname(doc), src))
                dest = os.path.normpath(os.path.join(tmp, str(di), src))
                if full in ep.names and dest.startswith(tmp):
                    os.makedirs(os.path.dirname(dest), exist_ok=True)
                    with open(dest, "wb") as f:
                        f.write(ep.read_bytes(full))
            os.makedirs(os.path.join(tmp, str(di)), exist_ok=True)
            page = os.path.join(tmp, str(di), "page.html")      # .html: Chrome's lenient parser
            with open(page, "w") as f:
                f.write(html)
            w, h = _page_size(html)
            jobs.append((os.path.join(tmp, f"chrome{di}"), page, os.path.join(tmp, f"{di:04d}.png"), w, h))
        pngs = []
        for i, job in enumerate(jobs):          # one at a time: parallel headless Chrome fights over its profile
            pngs.append(_render(job))
            if progress:
                progress(i + 1, len(jobs))
        pngs = [p for p in pngs if os.path.exists(p)]
        out = subprocess.run([OCR_BIN] + pngs, capture_output=True, text=True, timeout=3600).stdout.splitlines()
        blocks = []
        for png, line in zip(pngs, out):
            di = int(os.path.basename(png)[:4])
            for text in reading_order(json.loads(line)):
                blocks.append({"tag": "p", "cls": "", "parent": "", "text": extract.clean(text), "doc": di, "list": ""})
        os.makedirs(os.path.dirname(cache), exist_ok=True)
        with open(cache, "w") as f:
            json.dump(blocks, f)
        return blocks
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def reading_order(obs):
    """Vision line boxes → text lines in reading order. Columns are found from where lines start;
    fragments on the same row of a column (e.g. "2" + "Tbs. sugar") are glued back together."""
    obs = [dict(o) for o in obs if o["t"].strip()]
    if not obs:
        return []
    narrow = sorted(o["x"] for o in obs if o["w"] < 0.55)
    anchors = []
    for x in narrow:                       # chain line starts that sit close together into columns
        if anchors and x - anchors[-1][-1] < 0.035:
            anchors[-1].append(x)
        else:
            anchors.append([x])
    anchors = [c[0] for c in anchors if len(c) >= 2] or [0.0]

    def col_of(o):
        if o["w"] >= 0.55:
            return "full"
        return max([i for i, a in enumerate(anchors) if a <= o["x"] + 0.01] or [0])
    for o in obs:
        o["col"] = col_of(o)
    lines = []
    for o in sorted(obs, key=lambda o: (str(o["col"]), o["y"], o["x"])):
        def near(l):
            same_row = abs((l["y"] + l["h"] / 2) - (o["y"] + o["h"] / 2)) < 0.006
            gap = max(o["x"] - (l["x"] + l["w"]), l["x"] - (o["x"] + o["w"]))
            return l["col"] == o["col"] and same_row and gap < 0.06
        last = next((l for l in reversed(lines[-6:]) if near(l)), None)
        if last:
            if o["x"] < last["x"]:          # e.g. the "2" read after "Tbs. sugar"
                last["t"] = o["t"] + " " + last["t"]
            else:
                last["t"] += " " + o["t"]
            x0, x1 = min(last["x"], o["x"]), max(last["x"] + last["w"], o["x"] + o["w"])
            last["x"], last["w"] = x0, x1 - x0
        else:
            lines.append(o)
    lines.sort(key=lambda l: l["y"])
    out, band = [], []

    def flush():
        for col in sorted({l["col"] for l in band}):
            out.extend(l["t"] for l in sorted((l for l in band if l["col"] == col), key=lambda l: l["y"]))
        band.clear()
    for l in lines:
        if l["col"] == "full":
            flush()
            out.append(l["t"])
        else:
            band.append(l)
    flush()
    return [t for t in out if not re.fullmatch(r"(\d+\s+)?[A-Z -]{3,24}(\s+\d+)?", t.strip()) or len(t) > 30
            or not re.search(r"\d", t)]


# ------------------------------------------------------------------ positioned spans → lines

def spans_to_lines(blocks):
    """Collapse absolutely positioned span fragments (tag 'pos') into line blocks."""
    out, run = [], []

    def flush():
        if not run:
            return
        vs = [p["v"] for p in run]
        thr = max(1.0, 0.015 * (max(vs) - min(vs) + 1)) if len(run) > 3 else 1e9
        line, prev = [], None
        for p in run:
            dv = abs(p["v"] - prev["v"]) if prev else 0
            new = prev is not None and (dv > thr or (p["l"] < prev["l"] - 1 and dv > thr * 0.3))
            if new and line:
                out.append(_line(line, p["doc"]))
                line = []
            line.append(p)
            prev = p
        if line:
            out.append(_line(line, run[-1]["doc"]))
        run.clear()
    for b in blocks:
        if b["tag"] == "pos":
            if run and run[-1]["doc"] != b["doc"]:
                flush()
            run.append(b)
        else:
            flush()
            out.append(b)
    flush()
    return out


def _line(parts, doc):
    text = "".join(p["text"] for p in parts)
    text = re.sub(r"(\d)\s*[⁄/]\s*(\d)", r"\1/\2", text)
    return {"tag": "p", "cls": "", "parent": "", "text": " ".join(text.split()), "doc": doc, "list": "", "line": True}


# ------------------------------------------------------------------ lines → paragraphs

def looks_like_lines(blocks):
    """True when a book is mostly one CSS class of short line fragments (fixed layout)."""
    tb = [b for b in blocks if b["tag"] != "img"]
    if len(tb) < 200:
        return False
    if sum(1 for b in tb if b.get("line")) > 0.3 * len(tb):
        return True
    keys = {}
    for b in tb:
        k = extract._key(b)
        keys[k] = keys.get(k, 0) + 1
    top = max(keys.values())
    med = statistics.median(len(b["text"]) for b in tb)
    return top > 0.6 * len(tb) and med < 60


FOOTER = re.compile(r"^\d{1,3}\s+[A-Z]\s+\S.*|\S.*\s[A-Z]\s+\d{1,3}$|^(page\s*)?\d{1,3}$", re.I)
SECTION = re.compile(r"^(prepare ingredients|ingredients|gather (?:\w+ )?equipment|equipment|you(?:'ll| will)? need|"
                     r"what you need|tools|start (?:baking|cooking)!?|directions|method|instructions|let'?s (?:cook|bake)!?)$", re.I)
UNIT_START = re.compile(r"^(cups?|tbs\.?|tbsp\.?|tsp\.?|teaspoons?|tablespoons?|oz\.?|lbs?\.?|pounds?|ounces?|pinch|dash)\b", re.I)
STEP_START = re.compile(r"^(?:step\s*)?\d{1,2}[.)]?\s*$|^(?:step\s*)?\d{1,2}[.)]\s+\S|^[•●▪✦◆■]\s*", re.I)


def merge_lines(blocks):
    tb = [b for b in blocks if b["tag"] != "img"]
    long_lines = [len(b["text"]) for b in tb if len(b["text"]) > 25]
    typical = statistics.median(long_lines) if long_lines else 60
    out, cur = [], None

    def flush():
        nonlocal cur
        if cur:
            out.append(cur)
        cur = None
    for b in blocks:
        if b["tag"] == "img":
            flush()
            out.append(b)
            continue
        t = re.sub(r"^[Il|]\.\s", "1. ", b["text"].strip())     # OCR reads "1." as "I."
        if not t or FOOTER.search(t):
            continue
        if SECTION.match(t):
            flush()
            out.append(dict(b, text=t, _ing=False, _last=t, section=True))
            continue
        caps = t.isupper() and len(t) < 60 and not extract.YIELD_RE.match(t) and ":" not in t
        if cur and caps and cur["text"].isupper() and len(cur["text"]) < 60 and cur["doc"] == b["doc"] \
                and not extract.YIELD_RE.match(cur["text"]) and ":" not in cur["text"]:
            cur["text"] += " " + t                         # title wrapped over two all-caps lines
            cur["_last"] = t
            continue
        if caps:
            flush()
            cur = dict(b, text=t, _ing=False, _last=t)
            continue
        ing = extract.is_ingredient_like(t) and len(t) < 90
        if cur is None or b["doc"] != cur["doc"]:
            new = True
        elif re.fullmatch(r"(?:step\s*)?\d{1,2}[.)]?", cur["text"], re.I):
            new = False                                   # a bare "1." waits for its text
        elif STEP_START.match(t) or (extract.YIELD_RE.match(t) and t[0].isupper()) or extract.NOTE_HEAD_RE.match(t):
            new = True
        elif cur.get("_ing") and UNIT_START.match(t):
            new = True                                    # ingredient whose quantity OCR missed: "cup milk"
        elif t[0].islower() or cur["text"].endswith(("-", ",", "and", "or", "the", "a", "of", "to", "with", "about")):
            new = False                                   # obvious continuation
        elif not cur.get("_ing") and STEP_START.match(cur["text"]) and not re.search(r"[.!?:)]$", cur["text"]):
            new = False                                   # a numbered step that hasn't finished its sentence
        elif ing or cur.get("_ing"):
            new = True                                    # one ingredient per line
        elif len(cur["_last"]) < 0.7 * typical:
            new = True                                    # previous line stopped short → paragraph ended
        else:
            new = False
        if new:
            flush()
            cur = dict(b, text=t, _ing=ing, _last=t)
        else:
            joiner = "" if cur["text"].endswith("-") and t[:1].islower() else " "
            cur["text"] = (cur["text"][:-1] if joiner == "" else cur["text"]) + joiner + t
            cur["_last"] = t
            cur["_ing"] = cur["_ing"] and len(cur["text"]) < 90
    flush()
    # give the extractor class signals it can learn from
    for p in out:
        if p["tag"] == "img":
            continue
        t = p.pop("_last", None) and p["text"]
        p.pop("_ing", None)
        p["line"] = False
        if p.pop("section", False):
            p["cls"] = "fx-section"
        elif extract.YIELD_RE.match(p["text"]) or re.match(r"^[A-Z ]+:", p["text"]):
            p["cls"] = "fx-yield"
        elif p["text"].isupper() and 3 < len(p["text"]) < 80 and not extract.is_ingredient_like(p["text"]):
            p["cls"] = "fx-title"
        elif extract.is_ingredient_like(p["text"]) and len(p["text"]) < 110:
            p["cls"] = "fx-ing"
        elif STEP_START.match(p["text"]) or len(p["text"]) > 80:
            p["cls"] = "fx-step"
        elif len(p["text"]) <= 70:
            p["cls"] = "fx-head"
        else:
            p["cls"] = "fx"
        p["parent"] = ""
    # an all-caps line sitting between ingredient lines is a component heading ("STREUSEL TOPPING"), not a recipe
    txt = [p for p in out if p["tag"] != "img"]
    for i, p in enumerate(txt):
        if p.get("cls") == "fx-title" and 0 < i < len(txt) - 1 and txt[i - 1].get("cls") == "fx-ing" \
                and txt[i + 1].get("cls") == "fx-ing":
            p["cls"] = "fx-head"
    return out
