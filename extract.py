"""EPUB cookbook reader + recipe extractor (stdlib only).

Cookbooks don't share a markup standard, so extraction is learned per book:
1. Flatten every spine document into a stream of text blocks (tag, class, parent class, text).
2. Find runs of ingredient-like lines ("2 tablespoons olive oil").
3. Learn which CSS classes this publisher uses for ingredients, steps and recipe titles.
4. Cut the stream into recipes at title blocks and sort each recipe's blocks into
   meta / headnote / ingredients / steps / notes.
"""
import collections
import html
import os
import posixpath
import re
import zipfile
from html.parser import HTMLParser
from urllib.parse import unquote

BLOCK_TAGS = {"p", "h1", "h2", "h3", "h4", "h5", "h6", "li", "div", "td", "th", "dt", "dd",
              "blockquote", "figcaption", "caption", "section", "article", "aside", "header",
              "footer", "tr", "table", "ul", "ol", "body", "figure", "pre"}
SKIP_TAGS = {"script", "style", "head", "title"}
HEADINGS = {"h1", "h2", "h3", "h4", "h5", "h6"}

FRACTIONS = "½¼¾⅓⅔⅛⅜⅝⅞⅕⅖⅗⅘⅙⅚"
LEAD_JUNK = re.compile(r"^[\s•●▪■□◦✦✧*·–—\-]+")
QTY_RE = re.compile(
    r"^(?:[\d" + FRACTIONS + r"]|(?:one|two|three|four|five|six|eight|ten|twelve|a|an|half|several|"
    r"few|pinch|dash|handful|juice|zest|grated zest|kosher|fine|flaky|sea|table|freshly|fresh|"
    r"salt|pepper|black pepper|olive oil|vegetable oil|canola oil|cooking spray|nonstick|"
    r"water|ice|about|optional|for serving|to serve|for garnish|garnish|chopped|sliced|cups?|tbs|tbsp|tsp|"
    r"unsalted|butter|sugar|flour|lemon|lime)\b)", re.I)
UNIT_RE = re.compile(
    r"\b(cups?|c\.|tablespoons?|tbsp\.?|tbs|teaspoons?|tsp\.?|ounces?|oz\.?|pounds?|lbs?\.?|grams?|g|kg|"
    r"ml|milliliters?|liters?|l|cloves?|cans?|jars?|large|medium|small|pinch|dash|sprigs?|bunch(?:es)?|"
    r"stalks?|ribs?|slices?|sticks?|quarts?|qt|pints?|pt|whole|packages?|pkg|inch|heads?|leaves|"
    r"fillets?|pieces?|to taste|handful|bag|box|bottle|envelope|dozen)\b", re.I)
STEP_NUM_RE = re.compile(r"^(?:step\s*)?(?:\d{1,2}[.):]|[①-⑳❶-❿➀-➉])\s*", re.I)
STEP_WORD_NUM_RE = re.compile(r"^\d{1,2}\s+[A-Z][a-z]+\b")
YIELD_RE = re.compile(
    r"^(serves|serving|servings|makes|yield|yields|prep(?:aration)?(?: time)?|cook(?:ing)? time|"
    r"total(?: time)?|active(?: time)?|hands[- ]on|time|start to finish|ready in|bake time|"
    r"per serving|calories|nutrition|level|difficulty|pressure|release|setting|function)\b", re.I)
NOTE_HEAD_RE = re.compile(
    r"^(variations?|note|notes|tips?|cook'?s note|make ahead|make-ahead|to make ahead|storage|"
    r"store|serving suggestion|swap|substitution|try this|why this recipe works|the scoop|"
    r"perfect pairings|skinny scoop|freeze|to freeze|leftovers|do ahead|kid tip)\b", re.I)
NUTRI_RE = re.compile(
    r"^(calories|kcal|fat|total fat|sat(?:urated)?|carb|carbs|carbohydrates?|fiber|fibre|sugars?|protein|"
    r"sodium|cholesterol|potassium|iron|calcium|per serving|per portion|nutrition|smartpoints|points|"
    r"net carbs|vitamin|grams?)\b", re.I)
BAD_TITLE_RE = re.compile(r"^(back to|return to|see (page|p\.)|continued|recipe continues|cont\.|page \d|"
                          r"\d|about |approx|photo|photograph|image|figure|fig\.|table of contents|contents|"
                          r"index|copyright|ingredients|method|directions|instructions|preparation|"
                          r"equipment|for the|to serve|serve with|you will need|special equipment|instead of|sub |swap|make it|"
                          r"add more|simplify|the vibe|key equipment|gas mark|ounces|cups|grams|oven temp|converting|"
                          r"target weight|test kitchen tip|buying |shopping list|grocery list|✓|\(\s*\+|"
                          r".*\b(serves|makes|servings)\s+\d|useful equivalents|liquid \(|fl oz|granular|standard |fahrenheit|celsius|"
                          r"cooling$|conversion|measurements?$|metric|.*\(ex\.)", re.I)
SENTENCE_END = re.compile(r"[.!?]['\"’”)]?$")


# Some self-published ebooks swap Latin letters for Cyrillic look-alikes; fold them back so search works.
HOMOGLYPHS = str.maketrans("аеорсухіјѕԁԛԝАВЕКМНОРСТХІЈЅ", "aeopcyxijsdqwABEKMHOPCTXIJS")


def clean(text):
    text = re.sub(r"(\d)\s*⁄\s*(\d)", r"\1/\2", html.unescape(text).translate(HOMOGLYPHS))
    return " ".join(text.split())


def is_ingredient_like(t):
    if not t or len(t) > 160:
        return False
    s = LEAD_JUNK.sub("", t)
    if not s:
        return False
    if STEP_NUM_RE.match(s) and len(s) > 50:
        return False
    if STEP_WORD_NUM_RE.match(s) and len(s) > 60 and not UNIT_RE.search(s.split(" ", 2)[1]):
        return False
    if YIELD_RE.match(s):
        return False
    if s[0].isdigit() or s[0] in FRACTIONS:
        # "350°F" or page numbers are not ingredients
        if re.match(r"^\d+\s*°", s) or re.fullmatch(r"[\d\s().+-]+", s):
            return False
        return len(s) < 140
    if QTY_RE.match(s) and len(s) < 90 and not re.search(r"[a-z]{3,}[.!?] [A-Z]", s):
        return True
    return False


def is_step_like(t):
    s = LEAD_JUNK.sub("", t)
    if STEP_NUM_RE.match(s) and len(s) > 20:
        return True
    if STEP_WORD_NUM_RE.match(s) and len(s) > 50:
        return True
    return len(s) > 90 and bool(SENTENCE_END.search(s))


# ---------------------------------------------------------------- HTML -> blocks

class _BlockParser(HTMLParser):
    def __init__(self, doc_path):
        super().__init__(convert_charrefs=True)
        self.doc_dir = posixpath.dirname(doc_path)
        self.blocks = []
        self.stack = []      # open block elements
        self.skip = 0
        self.list_stack = []
        self.span_depth = 0
        self.pos = None          # open absolutely-positioned span: {"l", "v", "text", "depth"}

    def _cls(self, attrs):
        for k, v in attrs:
            if k == "class" and v:
                return v.split()[0]
        return ""

    def handle_starttag(self, tag, attrs):
        if tag in SKIP_TAGS:
            self.skip += 1
            return
        if self.skip:
            return
        if tag in ("img", "image"):
            src = None
            for k, v in attrs:
                if k in ("src", "xlink:href", "href"):
                    src = v
            if src:
                self._flush_top()
                self.blocks.append({"tag": "img", "src": posixpath.normpath(posixpath.join(self.doc_dir, unquote(src.split("#")[0]))),
                                    "alt": dict(attrs).get("alt") or ""})
            return
        if tag == "br":
            self._flush_top()
            return
        if tag == "span":
            self.span_depth += 1
            style = dict(attrs).get("style") or ""
            lm = re.search(r"left:\s*(-?[\d.]+)px", style)
            vm = re.search(r"(bottom|top):\s*(-?[\d.]+)px", style)
            if self.pos is None and lm and vm:
                self._flush_top()
                v = float(vm.group(2)) * (-1 if vm.group(1) == "bottom" else 1)
                self.pos = {"l": float(lm.group(1)), "v": v, "text": "", "depth": self.span_depth}
            return
        if tag in BLOCK_TAGS:
            self._flush_top()
            if tag in ("ul", "ol"):
                self.list_stack.append(tag)
            parent = self.stack[-1]["cls"] if self.stack else ""
            if not parent and len(self.stack) > 1:
                parent = self.stack[-2]["cls"]
            self.stack.append({"tag": tag, "cls": self._cls(attrs), "parent": parent, "buf": []})

    def handle_endtag(self, tag):
        if tag in SKIP_TAGS:
            self.skip = max(0, self.skip - 1)
            return
        if tag == "span":
            if self.pos and self.pos["depth"] == self.span_depth:
                if self.pos["text"].strip():
                    self.blocks.append({"tag": "pos", "l": self.pos["l"], "v": self.pos["v"],
                                        "text": html.unescape(self.pos["text"]).translate(HOMOGLYPHS)})
                self.pos = None
            self.span_depth = max(0, self.span_depth - 1)
            return
        if self.skip or tag not in BLOCK_TAGS:
            return
        # pop to the matching element (tolerate sloppy markup)
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i]["tag"] == tag:
                while len(self.stack) > i:
                    self._flush_top()
                    self.stack.pop()
                break
        if tag in ("ul", "ol") and self.list_stack:
            self.list_stack.pop()

    def handle_data(self, data):
        if self.skip:
            return
        if self.pos is not None:
            self.pos["text"] += data
            return
        if not self.stack:
            return
        self.stack[-1]["buf"].append(data)

    def _flush_top(self):
        if not self.stack:
            return
        top = self.stack[-1]
        text = clean("".join(top["buf"]))
        top["buf"] = []
        if text:
            self.blocks.append({"tag": top["tag"], "cls": top["cls"], "parent": top["parent"], "text": text,
                                "list": self.list_stack[-1] if self.list_stack else ""})

    def close(self):
        super().close()
        while self.stack:
            self._flush_top()
            self.stack.pop()


# ---------------------------------------------------------------- EPUB container

class Epub:
    def __init__(self, path):
        self.path = path
        self.z = zipfile.ZipFile(path)
        self.names = set(self.z.namelist())
        container = self.z.read("META-INF/container.xml").decode("utf8", "ignore")
        self.opf_path = unquote(re.search(r'full-path="([^"]+)"', container).group(1))
        self.opf_dir = posixpath.dirname(self.opf_path)
        opf = self.z.read(self.opf_path).decode("utf8", "ignore")
        self.opf = opf
        self.manifest = {}
        for m in re.finditer(r"<(?:\w+:)?item\b([^>]*)/?>", opf):
            a = dict(re.findall(r'([\w:-]+)\s*=\s*"([^"]*)"', m.group(1)))
            if "id" in a and "href" in a:
                a["full"] = posixpath.normpath(posixpath.join(self.opf_dir, unquote(a["href"])))
                self.manifest[a["id"]] = a
        self.spine = []
        for m in re.finditer(r"<(?:\w+:)?itemref\b([^>]*)/?>", opf):
            a = dict(re.findall(r'([\w:-]+)\s*=\s*"([^"]*)"', m.group(1)))
            it = self.manifest.get(a.get("idref"))
            if it and it["full"] in self.names:
                self.spine.append(it["full"])
        if not self.spine:
            self.spine = sorted(n for n in self.names if n.endswith((".xhtml", ".html", ".htm")))

    def meta(self, name):
        m = re.search(r"<dc:" + name + r"\b[^>]*>(.*?)</dc:" + name + ">", self.opf, re.S | re.I)
        return clean(re.sub(r"<[^>]+>", "", m.group(1))) if m else ""

    def cover_path(self):
        cands = []
        m = re.search(r'<meta\b[^>]*name="cover"[^>]*content="([^"]+)"', self.opf) or \
            re.search(r'<meta\b[^>]*content="([^"]+)"[^>]*name="cover"', self.opf)
        if m and m.group(1) in self.manifest:
            cands.append(self.manifest[m.group(1)]["full"])
        for it in self.manifest.values():
            if "cover-image" in it.get("properties", ""):
                cands.append(it["full"])
        for it in self.manifest.values():
            if it.get("media-type", "").startswith("image/") and "cover" in it["href"].lower():
                cands.append(it["full"])
        # first image referenced in the first spine doc
        if self.spine:
            first = self.read(self.spine[0])
            im = re.search(r'(?:src|xlink:href)="([^"]+\.(?:jpe?g|png|gif|webp))"', first, re.I)
            if im:
                cands.append(posixpath.normpath(posixpath.join(posixpath.dirname(self.spine[0]), unquote(im.group(1)))))
        for c in cands:
            if c in self.names and re.search(r"\.(jpe?g|png|gif|webp)$", c, re.I):
                return c
        return None

    def read(self, name):
        return self.z.read(name).decode("utf8", "ignore")

    def read_bytes(self, name):
        return self.z.read(name)

    def blocks(self):
        out = []
        for di, doc in enumerate(self.spine):
            p = _BlockParser(doc)
            try:
                p.feed(self.read(doc))
                p.close()
            except Exception:
                continue
            for b in p.blocks:
                b["doc"] = di
                out.append(b)
        if any(b["tag"] == "pos" for b in out):
            import fixedlayout
            out = fixedlayout.spans_to_lines(out)
        return out


# ---------------------------------------------------------------- recipe extraction

def _key(b):
    return b["tag"] + "." + (b.get("cls") or "^" + b.get("parent", ""))


def extract_recipes(blocks, names_info=None):
    """Return a list of recipe dicts from a flat block stream."""
    text_blocks = [b for b in blocks if b["tag"] != "img"]
    for b in text_blocks:
        b["ing"] = is_ingredient_like(b["text"])
        b["stp"] = is_step_like(b["text"])

    # class statistics -----------------------------------------------------
    stats = collections.defaultdict(lambda: [0, 0, 0, 0])   # n, ing, step, totlen
    pstats = collections.defaultdict(lambda: [0, 0])          # parent container: n, ing
    for b in text_blocks:
        s = stats[_key(b)]
        s[0] += 1; s[1] += b["ing"]; s[2] += b["stp"]; s[3] += len(b["text"])
        if b.get("parent"):
            ps = pstats[b["tag"] + "<" + b["parent"]]
            ps[0] += 1; ps[1] += b["ing"]

    def classy(k):
        return not k.endswith(".^")

    ing_keys = {k for k, (n, i, s, L) in stats.items()
                if n >= 6 and i / n >= 0.5 and L / n < 110 and classy(k)}
    ing_parents = {k for k, (n, i) in pstats.items() if n >= 8 and i / n >= 0.6}

    def is_ing(b):
        if b["tag"] == "img" or b["tag"] in HEADINGS:
            return False
        k = _key(b)
        if k in ing_keys:
            return not YIELD_RE.match(b["text"]) and len(b["text"]) < 220
        if b.get("parent") and (b["tag"] + "<" + b["parent"]) in ing_parents and len(b["text"]) < 160 \
                and not b["stp"] and not YIELD_RE.match(b["text"]):
            return True
        n = stats[k][0]
        if n >= 25 and stats[k][1] / n < 0.15:   # a body-text class: don't trust the regex
            return False
        return b["ing"]

    seq = blocks
    flags = [is_ing(b) for b in seq]

    # ingredient runs (allow short sub-headers / blanks between lines) ----------
    runs = []
    i = 0
    while i < len(seq):
        if flags[i]:
            j, last, count = i, i, 0
            while j < len(seq) and j - last <= 3 and seq[j]["doc"] == seq[i]["doc"]:
                if flags[j]:
                    last = j; count += 1
                elif seq[j]["tag"] != "img" and (seq[j]["stp"] or len(seq[j]["text"]) > 70):
                    break
                j += 1
            if count >= 2:
                runs.append((i, last))
            i = last + 1
        else:
            i += 1

    # learn step + title classes from neighbourhoods of runs ------------------
    text_count = collections.Counter(b["text"].lower() for b in text_blocks)

    def good_title(b):
        t = b["text"]
        return (3 <= len(t) <= 110 and len(re.findall(r"[A-Za-zÀ-ÿ]", t)) >= 3
                and text_count[t.lower()] <= 4 and not YIELD_RE.match(t) and not NUTRI_RE.match(t)
                and not NOTE_HEAD_RE.match(t) and not BAD_TITLE_RE.match(t) and not t.endswith(":")
                and not re.search(r":\s*[\d" + FRACTIONS + "]", t)
                and not t.startswith(("“", '"', "‘", "'", "—")) and not re.search(r"—\s*\w+\s*,\s*\d+\s*$|\s,\s*\d+$", t)
                and b.get("cls") != "fx-section"
                and not (SENTENCE_END.search(t) and len(t) > 60) and not b["stp"])

    step_votes = collections.Counter()
    for a, z in runs:
        seen = set()
        for j in range(z + 1, min(len(seq), z + 6)):
            b = seq[j]
            if b["tag"] == "img" or flags[j]:
                continue
            if len(b["text"]) > 50 or b["stp"]:
                k = _key(b)
                if k not in seen:
                    step_votes[k] += 1; seen.add(k)
    nr = max(1, len(runs))
    step_keys = {k for k, v in step_votes.items() if v >= max(2, 0.12 * nr) and k not in ing_keys}

    def window(ri):
        a = runs[ri][0]
        lo = max(0, a - 40)
        if ri:
            lo = max(lo, runs[ri - 1][1] + 1)
        for j in range(a - 1, lo - 1, -1):
            b = seq[j]
            if b["tag"] == "img" or flags[j]:
                continue
            yield j, b

    title_votes = collections.Counter()
    for ri in range(len(runs)):
        best = None
        for j, b in window(ri):
            if j < runs[ri][0] - 15:
                break
            if _key(b) in step_keys and b["stp"]:
                break   # previous recipe's method
            if good_title(b):
                best = b      # keep walking back: the title sits above subtitles / yields
        if best is not None:
            title_votes[_key(best)] += 1 + (best["tag"] in HEADINGS)
    title_keys = {k for k, v in title_votes.items()
                  if v >= max(2, 0.12 * nr) and k not in ing_keys and k not in step_keys
                  and stats[k][3] / max(1, stats[k][0]) < 90}

    fx_titles = {_key(b) for b in seq if b.get("cls") == "fx-title"}
    if len([b for b in seq if b.get("cls") == "fx-title"]) >= 5:
        title_keys = fx_titles            # fixed-layout book: the all-caps headings are the titles
    title_idx = []
    if title_keys:
        title_idx = [j for j, b in enumerate(seq)
                     if b["tag"] != "img" and _key(b) in title_keys and good_title(b)]
    # runs with no title-class block in front of them get the nearest plausible line
    for ri, (a, z) in enumerate(runs):
        lo = runs[ri - 1][1] if ri else -1
        if any(lo < t < a for t in title_idx):
            continue
        for j, b in window(ri):
            if j < a - 12:
                break
            if good_title(b) and not SENTENCE_END.search(b["text"]):
                title_idx.append(j)
                break
    SUB = re.compile(r"^(with |\(|\+ |and |aka )", re.I)
    fixed = []
    for j in title_idx:
        if SUB.match(seq[j]["text"]):
            k = j - 1
            while k >= 0 and seq[k]["tag"] == "img":
                k -= 1
            if k >= 0 and good_title(seq[k]):
                j = k
        fixed.append(j)
    title_idx = sorted(set(fixed))

    # Photos: some books put the dish photo (often with a caption repeating the title) just
    # *before* the recipe, others inside it. Look at the run of images / short captions right
    # above each title; that run belongs to this recipe, not to the one before it.
    def pre_window(n, t):
        lo = title_idx[n - 1] if n else -1
        imgs, j, caption = [], t - 1, False
        tnorm = re.sub(r"\W+", "", seq[t]["text"].lower())
        while j > lo and t - j <= 6:
            b = seq[j]
            if b["tag"] == "img":
                imgs.append(b["src"])
            elif flags[j] or b["stp"] or len(b["text"]) > 120:
                break
            elif re.sub(r"\W+", "", b["text"].lower()) == tnorm:
                caption = True
            elif not imgs and t - j > 2:
                break
            j -= 1
        return imgs[::-1], j + 1, caption

    windows = [pre_window(n, t) for n, t in enumerate(title_idx)]
    recipes = []
    for n, t in enumerate(title_idx):
        end = title_idx[n + 1] if n + 1 < len(title_idx) else len(seq)
        if n + 1 < len(title_idx) and windows[n + 1][0]:
            end = min(end, windows[n + 1][1])      # the next recipe's photo + caption aren't ours
        end = min(end, t + 260)
        rec = _build(seq[t:end], flags[t:end], step_keys)
        if rec:
            rec["pre_images"] = windows[n][0]
            rec["_caption"] = windows[n][2]
            recipes.append(rec)
    # book style: photos-before-title if that's where most recipe photos live
    pre_n = sum(1 for r in recipes if r["pre_images"])
    in_n = sum(1 for r in recipes if r["images"])
    caption_n = sum(1 for r in recipes if r["_caption"])
    photos_first = pre_n and (pre_n >= in_n or caption_n >= 0.3 * pre_n)
    for r in recipes:
        if photos_first and r["pre_images"]:
            r["images"] = r["pre_images"] + [i for i in r["images"] if i not in r["pre_images"]]
        r.pop("pre_images"); r.pop("_caption")
    return _dedupe(recipes)


EQUIP_HEAD = re.compile(r"^(gather (?:\w+ )?equipment|equipment|special equipment|you(?:'ll| will)? need|what you need|tools)\b", re.I)


def _build(blocks, flags, step_keys):
    title_b = blocks[0]
    title = title_b["text"]
    if len(blocks) > 1 and blocks[1]["tag"] != "img" and len(blocks[1]["text"]) < 80 and \
            re.match(r"^(with |\(|\+ |and |aka )", blocks[1]["text"], re.I):
        title = title + " " + blocks[1]["text"]
        blocks, flags = blocks[1:], flags[1:]
    meta, headnote, ingredients, steps, notes, images = [], [], [], [], [], []
    phase = "head"          # head -> ing -> steps -> notes
    doc0 = title_b["doc"]
    paged = str(title_b.get("cls", "")).startswith("fx")   # fixed-layout: one page per doc, recipes span pages
    equipment = []
    for b, f in zip(blocks[1:], flags[1:]):
        if b["tag"] == "img":
            if phase != "notes":
                images.append(b["src"])
            continue
        t = b["text"]
        if b["doc"] != doc0 and phase in ("steps", "notes") and not paged:
            break
        if EQUIP_HEAD.match(t) and len(t) < 40:
            phase_before_equip, phase = phase, "equip"
            continue
        if phase == "equip":
            if STEP_NUM_RE.match(t) or len(t) > 120:
                phase = "steps"
            else:
                equipment.append(t)
                continue
        if b.get("cls") == "fx-section":
            continue
        if b["tag"] in ("h1",) and phase != "head":
            break
        if phase == "head":
            if f:
                phase = "ing"
            elif YIELD_RE.match(t) and len(t) < 120:
                meta.append(t); continue
            elif len(t) < 40 and not SENTENCE_END.search(t) and not headnote:
                meta.append(t); continue
            else:
                headnote.append(t); continue
        if phase == "ing":
            if f:
                ingredients.append({"t": LEAD_JUNK.sub("", t)})
                continue
            if len(t) <= 60 and not STEP_NUM_RE.match(t) and not b["stp"] and _key(b) not in step_keys:
                if YIELD_RE.match(t):
                    meta.append(t)
                else:
                    ingredients.append({"t": t.rstrip(":"), "h": 1})
                continue
            phase = "steps"
        if phase == "steps":
            if NOTE_HEAD_RE.match(t) or (b["tag"] in HEADINGS and len(t) < 60 and steps):
                phase = "notes"; notes.append(t); continue
            k = _key(b)
            if paged and (t.startswith(("“", '"')) or re.search(r"—\s*\w+\s*,\s*\d+\s*$", t)):
                continue                       # kid-tester / reader quotes
            if k in step_keys or b["stp"] or STEP_NUM_RE.match(t) or (not step_keys and len(t) > 25):
                steps.append({"t": STEP_NUM_RE.sub("", LEAD_JUNK.sub("", t)) or t, "n": bool(STEP_NUM_RE.match(LEAD_JUNK.sub("", t))), "raw": LEAD_JUNK.sub("", t)})
            elif len(t) <= 60 and t.endswith(":"):
                steps.append({"t": t.rstrip(":"), "h": 1})
            elif f or len(t) < 25:
                if steps:
                    phase = "notes"; notes.append(t)
            else:
                steps.append({"t": t})
            continue
        if phase == "notes":
            if paged and STEP_NUM_RE.match(t):
                steps.append({"t": STEP_NUM_RE.sub("", t) or t, "n": True, "raw": t})   # recipe resumes after a page break
            elif len(notes) < 25:
                notes.append(t)
    # trim trailing sub-headers that were really the start of the method
    while ingredients and ingredients[-1].get("h"):
        ingredients.pop()
    if paged and sum(1 for s in steps if s.get("n")) >= 2:
        # follow the step numbers 1, 2, 3…; anything else (sidebars, photo how-tos, tips) becomes a note
        keep, extra, want = [], [], 1
        for s in steps:
            m = re.match(r"\D*(\d{1,2})", s.get("raw", "")) if s.get("n") else None
            if m and (int(m.group(1)) == want or (int(m.group(1)) == want + 1 and keep)):
                keep.append(s); want = int(m.group(1)) + 1      # tolerate one misread/missing number
            elif not s.get("h"):
                extra.append(s["t"])
        if len(keep) < 2:          # numbering unreadable: fall back to every numbered step in order
            keep = [s for s in steps if s.get("n")]
            extra = [s["t"] for s in steps if not s.get("n") and not s.get("h")]
        steps, notes = keep, notes + extra
    for s in steps:
        s.pop("n", None); s.pop("raw", None)
    if equipment:
        notes = ["Equipment: " + ", ".join(equipment)] + notes
    real_ing = [i for i in ingredients if not i.get("h")]
    real_steps = [s for s in steps if not s.get("h")]
    if len(real_ing) < 2 or not real_steps:
        return None
    if len(title) > 110 or is_ingredient_like(title) and not title[0].isalpha():
        return None
    if title.isupper() or title.islower():
        title = smart_title(title)
    return {"title": title, "meta": meta[:6], "headnote": headnote[:6], "ingredients": ingredients[:80],
            "steps": steps[:60], "notes": notes, "images": images[:4], "doc": title_b["doc"]}


SMALL = {"a", "an", "and", "as", "at", "but", "by", "for", "in", "of", "on", "or", "the", "to", "with", "n", "à", "la", "de", "en", "au"}


def smart_title(s):
    words = s.lower().split()
    out = []
    for i, w in enumerate(words):
        if i and w in SMALL:
            out.append(w)
        else:
            out.append(w[:1].upper() + w[1:] if w[:1].isalpha() else w[:2].upper() + w[2:] if w[:1] in "(\"'“‘" else w)
    return " ".join(out)


def _dedupe(recipes):
    seen, out = set(), []
    for r in recipes:
        k = (r["title"].lower(), r["ingredients"][0]["t"].lower() if r["ingredients"] else "")
        if k in seen:
            continue
        seen.add(k)
        out.append(r)
    return out


def parse_book(path):
    ep = Epub(path)
    blocks = ep.blocks()
    # drop ornaments, icons and repeated decorations so only real photos are considered
    uses = collections.Counter(b["src"] for b in blocks if b["tag"] == "img")

    def real_photo(src):
        try:
            return ep.z.getinfo(src).file_size > 25_000 and uses[src] <= 2
        except KeyError:
            return False
    blocks = [b for b in blocks if b["tag"] != "img" or real_photo(b["src"])]
    import fixedlayout
    text_chars = sum(len(b["text"]) for b in blocks if b["tag"] != "img")
    fixed = False
    if text_chars < 2000 and len(ep.spine) >= 10:
        blocks = fixedlayout.merge_lines(fixedlayout.ocr_book(ep))     # text drawn as outlines → OCR
        fixed = True
    elif fixedlayout.looks_like_lines(blocks):
        blocks = fixedlayout.merge_lines(blocks)
        fixed = True
    recipes = extract_recipes(blocks)
    if fixed:
        strip_running_heads(recipes)
        recipes = [r for r in recipes if not BAD_TITLE_RE.match(r["title"]) and len(r["title"]) > 2]
    return ep, recipes


def strip_running_heads(recipes):
    """Page headers ("SIDEDISHES", "Air Fryer Snacks") that got glued onto titles: a leading
    phrase shared by several titles, in front of an otherwise complete title, gets removed."""
    counts = collections.Counter()
    for r in recipes:
        w = r["title"].split()
        for k in (1, 2, 3):
            if len(w) > k + 1:
                counts[" ".join(w[:k]).lower()] += 1
    heads = sorted((p for p, n in counts.items() if n >= 3 and not p.endswith("-") and not re.search(r"\d", p)),
                   key=len, reverse=True)
    for r in recipes:
        low = r["title"].lower()
        for h in heads:
            if low.startswith(h + " ") and h not in ("air", "air fryer", "air-fryer", "air-fried", "easy", "quick", "mini"):
                r["title"] = r["title"][len(h) + 1:].strip()
                break
        r["title"] = re.sub(r"^(app|sid|appetizero?s?|sidedish(es)?|breakfast|dessert|over)\s+(?=[A-Z])", "", r["title"], flags=re.I)


if __name__ == "__main__":
    import sys, json
    ep, recs = parse_book(sys.argv[1])
    print(ep.meta("title"), "|", ep.meta("creator"), "| cover:", ep.cover_path(), "|", len(recs), "recipes")
    for r in recs[: int(sys.argv[2]) if len(sys.argv) > 2 else 5]:
        print(json.dumps(r, ensure_ascii=False, indent=1)[:1800])
