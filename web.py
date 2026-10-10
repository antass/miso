"""Web recipe sources: NYT Cooking search, EatingWell search, and schema.org Recipe import from any URL."""
import gzip
import hashlib
import html
import json
import re
import urllib.error
import urllib.parse
import urllib.request

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/129.0 Safari/537.36")


class Blocked(Exception):
    def __init__(self, site):
        super().__init__(site)
        self.site = site


def fetch(url, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html,application/xhtml+xml",
                                               "Accept-Language": "en-US,en;q=0.9"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = r.read()
    if data[:2] == b"\x1f\x8b":     # some CDNs gzip even when not asked
        data = gzip.decompress(data)
    return data.decode("utf8", "ignore")


def site_name(url):
    host = urllib.parse.urlparse(url or "").netloc.lower().replace("www.", "")
    return {"cooking.nytimes.com": "NYT Cooking", "nytimes.com": "NYT Cooking",
            "eatingwell.com": "EatingWell"}.get(host, host)


# ------------------------------------------------------------------ search

def search_nyt(q):
    s = fetch("https://cooking.nytimes.com/search?q=" + urllib.parse.quote(q))
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', s, re.S)
    if not m:
        return []
    out, seen = [], set()

    def walk(o):
        if isinstance(o, dict):
            url = o.get("url")
            if o.get("type") == "recipe" and isinstance(url, str) and url.startswith("/recipes/") and url not in seen:
                seen.add(url)
                img = ((o.get("image") or {}).get("src") or {}).get("card")
                out.append({"title": o.get("title") or o.get("name"), "url": "https://cooking.nytimes.com" + url,
                            "image": img, "byline": (o.get("contentAttribution") or {}).get("cardByline"),
                            "time": o.get("time"), "rating": (o.get("ratings") or {}).get("avgRating"),
                            "ratingCount": (o.get("ratings") or {}).get("numRatings"),
                            "site": "NYT Cooking"})
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(json.loads(m.group(1)))
    return [r for r in out if r["title"]][:40]


def search_eatingwell(q):
    """Parse EatingWell's own search page; keep recipe cards (old /recipe/ URLs or cards with a star rating)."""
    s = fetch("https://www.eatingwell.com/search?q=" + urllib.parse.quote_plus(q))
    out, seen = [], set()
    for m in re.finditer(r'<a [^>]*class="[^"]*mntl-card[^"]*"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', s, re.S):
        href, body = m.group(1), m.group(2)
        if href in seen or re.search(r"/(gallery|article|news)/", href):
            continue
        if "/recipe/" not in href and "star" not in body:
            continue
        t = re.search(r"card__title-text[^>]*>(.*?)<", body, re.S)
        if not t:
            continue
        seen.add(href)
        img = re.search(r'data-src="([^"]+)"', body) or re.search(r'<img[^>]+src="([^"]+)"', body)
        by = re.search(r'data-byline="([^"]*)"', body)
        stars = None
        sr = re.search(r'mntl-recipe-star-rating.*?</div>', body, re.S)
        if sr:
            full = len(re.findall(r'class="icon icon-star\s*"', sr.group(0)))
            half = len(re.findall(r'icon-star-half', sr.group(0)))
            stars = full + 0.5 * half or None
        tm = re.search(r'card-meta__time-text[^>]*>\s*([^<]+?)\s*<', body)
        out.append({"title": html.unescape(t.group(1)).strip(), "url": href, "image": img.group(1) if img else None,
                    "byline": html.unescape(by.group(1)) if by else "", "site": "EatingWell",
                    "rating": stars, "time": tm.group(1) if tm else None})
    return out[:40]


# ------------------------------------------------------------------ import

def _text(x):
    if x is None:
        return ""
    if isinstance(x, (int, float)):
        return str(x)
    if isinstance(x, list):
        return _text(x[0]) if x else ""
    if isinstance(x, dict):
        return _text(x.get("name") or x.get("text") or x.get("@value") or "")
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", str(x))).split())


def _image(x):
    if isinstance(x, str):
        return x
    if isinstance(x, list) and x:
        # prefer the biggest of a list of ImageObjects
        best = max(x, key=lambda i: int((i.get("width") or 0)) if isinstance(i, dict) else 0)
        return _image(best)
    if isinstance(x, dict):
        return x.get("url") or x.get("contentUrl")
    return None


def _duration(iso):
    m = re.match(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?", iso or "")
    if not m or not any(m.groups()):
        return ""
    d, h, mi = (int(g or 0) for g in m.groups())
    h += d * 24
    return " ".join(p for p in (f"{h} hr" if h else "", f"{mi} min" if mi else "") if p)


def _steps(ins):
    out = []
    if isinstance(ins, dict):          # a lone HowToStep / HowToSection instead of a list
        ins = [ins]
    if isinstance(ins, str):
        parts = [p for p in re.split(r"\n+|(?<=\.)\s{2,}", html.unescape(re.sub(r"<[^>]+>", "\n", ins))) if p.strip()]
        return [{"t": " ".join(p.split())} for p in parts]
    for it in ins or []:
        if isinstance(it, str):
            out.append({"t": _text(it)})
        elif isinstance(it, dict):
            if "HowToSection" in str(it.get("@type")):
                if it.get("name"):
                    out.append({"t": _text(it["name"]), "h": 1})
                out.extend(_steps(it.get("itemListElement")))
            else:
                t = _text(it.get("text") or it.get("name"))
                if t:
                    out.append({"t": t})
    return out


def find_recipe(ld_blobs):
    def walk(o):
        if isinstance(o, list):
            for v in o:
                r = walk(v)
                if r:
                    return r
        elif isinstance(o, dict):
            t = o.get("@type")
            if t == "Recipe" or (isinstance(t, list) and "Recipe" in t):
                return o
            for k in ("@graph", "mainEntity", "itemListElement"):
                if k in o:
                    r = walk(o[k])
                    if r:
                        return r
        return None

    for blob in ld_blobs:
        try:
            data = json.loads(blob) if isinstance(blob, str) else blob
        except Exception:
            continue
        r = walk(data)
        if r:
            return r
    return None


def import_recipe(url, ld=None):
    if ld:
        blobs = ld if isinstance(ld, list) else [ld]
    else:
        if not url:
            raise ValueError("No URL")
        try:
            page = fetch(url)
        except urllib.error.HTTPError as e:
            if e.code in (401, 403, 429):
                raise Blocked(site_name(url))
            raise
        blobs = re.findall(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', page, re.S)
        if not blobs and "Simple Page" in page[:2000]:
            raise Blocked(site_name(url))
    r = find_recipe(blobs)
    if not r:
        raise ValueError("Couldn't find a recipe on that page")
    url = url or r.get("url") or ""
    ingredients = [{"t": _text(i)} for i in (r.get("recipeIngredient") or r.get("ingredients") or []) if _text(i)]
    meta = []
    y = r.get("recipeYield")
    if y:
        y = _text(y if not isinstance(y, list) else y[-1])
        meta.append(y if re.search(r"[a-z]", y, re.I) else f"Serves {y}")
    for label, key in (("Total", "totalTime"), ("Prep", "prepTime"), ("Cook", "cookTime")):
        d = _duration(r.get(key))
        if d:
            meta.append(f"{label} {d}")
            if key == "totalTime":
                break
    nutrition = r.get("nutrition") or {}
    notes = []
    if isinstance(nutrition, dict) and nutrition.get("calories"):
        notes.append("Calories: " + _text(nutrition["calories"]) + " per serving")
    rating = None
    ar = r.get("aggregateRating")
    if isinstance(ar, dict) and ar.get("ratingValue"):
        try:
            rating = {"value": round(float(ar["ratingValue"]), 1),
                      "count": int(float(ar.get("ratingCount") or ar.get("reviewCount") or 0))}
        except (TypeError, ValueError):
            rating = None
    author = r.get("author")
    author = ", ".join(_text(a) for a in author) if isinstance(author, list) else _text(author)
    return {
        "id": "w-" + hashlib.sha1(url.encode()).hexdigest()[:10],
        "source": "web",
        "title": _text(r.get("name")),
        "site": site_name(url),
        "url": url,
        "author": author,
        "image": _image(r.get("image")),
        "rating": rating,
        "meta": meta,
        "headnote": [_text(r.get("description"))] if r.get("description") else [],
        "ingredients": ingredients,
        "steps": _steps(r.get("recipeInstructions")),
        "notes": notes,
        "images": [],
    }
