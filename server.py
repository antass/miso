#!/usr/bin/env python3
"""Miso — a local cookbook server.

Run:  python3 server.py            (http://localhost:8137)
      python3 server.py --lan      (also reachable from an iPad/phone on the same Wi-Fi)

Stdlib only. Indexes EPUB (and MOBI/AZW3 via Calibre) cookbooks, serves the web app in ./static.
"""
import glob
import gzip
import hashlib
import io
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
import traceback
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import extract
import facets
import web

APP_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC = os.path.join(APP_DIR, "static")
CONFIG_PATH = os.path.join(APP_DIR, "config.json")
STATE_PATH = os.path.join(APP_DIR, "data", "state.json")
CACHE = os.path.expanduser("~/Library/Application Support/Miso")
INDEX_VERSION = 5

DEFAULT_CONFIG = {
    "port": 8137,
    # Globs are allowed: GoogleDrive-* matches every account signed in to Google Drive for Desktop.
    "library_folders": [
        "~/Library/CloudStorage/GoogleDrive-anna.krentowicz@gmail.com/My Drive/AllBooks/eBooks/Cookbooks",
    ],
    # Folders that hold all kinds of books (e.g. a Calibre library): EPUBs only, and a book
    # only counts as a cookbook if it yields at least `min_recipes_mixed` recipes.
    "mixed_folders": [],
    "min_recipes_mixed": 10,
    "extensions": [".epub", ".mobi", ".azw3", ".azw"],
}

EBOOK_CONVERT = shutil.which("ebook-convert") or "/Applications/calibre.app/Contents/MacOS/ebook-convert"


def load_config():
    if not os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "w") as f:
            json.dump(DEFAULT_CONFIG, f, indent=2)
    with open(CONFIG_PATH) as f:
        cfg = {**DEFAULT_CONFIG, **json.load(f)}
    expand = lambda ps: sorted({m for p in ps for m in (glob.glob(os.path.expanduser(p)) or [os.path.expanduser(p)])})
    cfg["library_folders"] = expand(cfg["library_folders"])
    cfg["mixed_folders"] = expand(cfg.get("mixed_folders", []))
    return cfg


def norm_title(s):
    s = re.sub(r"\(.*?\)|&#\d+;|[®™]", "", s.lower())
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


# ------------------------------------------------------------------ library index

class Library:
    def __init__(self, cfg):
        self.cfg = cfg
        self.books = {}        # id -> book dict
        self.recipes = {}      # id -> recipe dict (with search fields)
        self.order = []        # recipe ids
        self.problems = []     # [{file, reason}]
        self.status = {"state": "idle", "done": 0, "total": 0, "current": ""}
        self.lock = threading.Lock()
        os.makedirs(os.path.join(CACHE, "books"), exist_ok=True)
        os.makedirs(os.path.join(CACHE, "covers"), exist_ok=True)
        os.makedirs(os.path.join(CACHE, "converted"), exist_ok=True)

    def files(self):
        """[(path, mixed)] — one file per book directory, preferring EPUB over Kindle formats."""
        out = []
        roots = [(r, False) for r in self.cfg["library_folders"]] + [(r, True) for r in self.cfg["mixed_folders"]]
        for root, mixed in roots:
            if not os.path.isdir(root):
                continue
            exts = [".epub"] if mixed else self.cfg["extensions"]
            for dp, dn, fn in os.walk(root):
                dn[:] = [d for d in dn if not d.startswith(".")]
                books = [f for f in fn if os.path.splitext(f)[1].lower() in exts and not f.startswith(".")]
                stems = {os.path.splitext(f)[0] for f in books if f.lower().endswith(".epub")}
                for f in books:
                    if not f.lower().endswith(".epub") and os.path.splitext(f)[0] in stems:
                        continue
                    out.append((os.path.join(dp, f), mixed))
        return out

    def start(self):
        t = threading.Thread(target=self._index_all, daemon=True)
        t.start()

    def _index_all(self):
        files = self.files()
        self.status = {"state": "indexing", "done": 0, "total": len(files), "current": ""}
        books, problems = {}, []
        for i, (path, mixed) in enumerate(files):
            self.status["current"] = os.path.basename(path)
            try:
                book = self._load_book(path)
                if mixed and (book is None or book["count"] < self.cfg["min_recipes_mixed"]):
                    pass        # not a cookbook
                elif book is None:
                    problems.append({"file": os.path.basename(path), "reason": "No recipes found"})
                else:
                    key = norm_title(book["title"])
                    prev = books.get(key)
                    if not prev or book["count"] > prev["count"]:
                        books[key] = book
            except Exception as e:
                if not mixed:
                    problems.append({"file": os.path.basename(path), "reason": _friendly_error(e)})
            self.status["done"] = i + 1
            self._publish(books, problems)   # make results searchable as they arrive
        have = {norm_title(os.path.splitext(b["path"])[0].split("/")[-1].split(" - ")[0]) for b in books.values()} | set(books)
        problems = [p for p in problems if norm_title(os.path.splitext(p["file"])[0].split(" - ")[0]) not in have]
        self._publish(books, problems)
        self.status = {"state": "ready", "done": len(files), "total": len(files), "current": ""}
        threading.Thread(target=self._warm_thumbs, daemon=True).start()

    def _warm_thumbs(self):
        """Pre-build card thumbnails so photos appear instantly when browsing."""
        with self.lock:
            todo = [(self.books[r["book"]], r["images"][0]) for r in self.recipes.values() if r.get("images")]
        for b, src in todo:
            thumb = os.path.join(CACHE, "thumbs", hashlib.sha1(f"{b['id']}|{src}|320".encode()).hexdigest() + ".jpg")
            if os.path.exists(thumb):
                continue
            try:
                os.makedirs(os.path.dirname(thumb), exist_ok=True)
                tmp = thumb + ".warm"
                with open(tmp, "wb") as f:
                    f.write(epub_for(b).read_bytes(src))
                subprocess.run(["sips", "-Z", "320", "-s", "format", "jpeg", "-s", "formatOptions", "75", tmp, "--out", thumb],
                               capture_output=True, timeout=60)
                os.remove(tmp)
            except Exception:
                pass

    def _publish(self, books_by_title, problems):
        books, recipes, order = {}, {}, []
        for b in sorted(books_by_title.values(), key=lambda b: b["title"].lower()):
            books[b["id"]] = {k: v for k, v in b.items() if k != "recipes"}
            for n, r in enumerate(b["recipes"]):
                rid = f"{b['id']}-{n}"
                r = dict(r, id=rid, book=b["id"], source="book")
                r["_t"] = r["title"].lower()
                r["_i"] = " | ".join(i["t"] for i in r["ingredients"] if not i.get("h")).lower()
                r["_b"] = b["title"].lower()
                r["_f"] = facets.compute(r, b["title"])
                recipes[rid] = r
                order.append(rid)
        with self.lock:
            self.books, self.recipes, self.order, self.problems = books, recipes, order, problems

    def _load_book(self, path):
        st = os.stat(path)
        bid = hashlib.sha1(path.encode()).hexdigest()[:10]
        sig = f"{INDEX_VERSION}:{st.st_size}:{int(st.st_mtime)}"
        cache_file = os.path.join(CACHE, "books", bid + ".json")
        if os.path.exists(cache_file):
            with open(cache_file) as f:
                cached = json.load(f)
            if cached.get("sig") == sig:
                return cached if cached.get("count") else None
        if st.st_size == 0:
            raise ValueError("File is empty (0 bytes)")
        epub_path = self._as_epub(path, bid)
        ep, recipes = extract.parse_book(epub_path)
        # drop icons / decorations: keep recipe photos over ~25 KB
        for r in recipes:
            keep = []
            for src in r["images"]:
                try:
                    if ep.z.getinfo(src).file_size > 25_000:
                        keep.append(src)
                except KeyError:
                    pass
            r["images"] = keep[:2]
        cover = ep.cover_path()
        if cover:
            ext = os.path.splitext(cover)[1].lower()
            with open(os.path.join(CACHE, "covers", bid + ext), "wb") as f:
                f.write(ep.read_bytes(cover))
            cover = bid + ext
        title = ep.meta("title") or os.path.splitext(os.path.basename(path))[0]
        title = re.sub(r"\s*[:–—]\s*.*$", "", title) if len(title) > 60 else title
        book = {"id": bid, "sig": sig, "path": path, "epub": epub_path, "title": extract.clean(title),
                "author": ep.meta("creator"), "cover": cover, "count": len(recipes), "recipes": recipes}
        with open(cache_file, "w") as f:
            json.dump(book, f)
        return book if recipes else None

    def _as_epub(self, path, bid):
        if path.lower().endswith(".epub"):
            return path
        out = os.path.join(CACHE, "converted", bid + ".epub")
        if not os.path.exists(out) or os.path.getmtime(out) < os.path.getmtime(path):
            if not os.path.exists(EBOOK_CONVERT):
                raise RuntimeError("MOBI needs Calibre (ebook-convert) installed")
            subprocess.run([EBOOK_CONVERT, path, out], check=True, capture_output=True, timeout=600)
        return out

    # --------------------------------------------------------------- queries

    # ---- search engine: free text + facet filters + user tags, with live facet counts
    GROUPS = {"course": "or", "protein": "or", "method": "or", "book": "or", "diet": "and", "tag": "and"}
    TIME_BUCKETS = [15, 30, 45, 60, 90]

    def search(self, p, web_recipes=(), tags=None, my_ratings=None):
        tags = tags or {}
        my_ratings = my_ratings or {}
        minrating = p.get("rating") or ""

        def rating_of(r):
            if r["id"] in my_ratings:
                return float(my_ratings[r["id"]])
            return float((r.get("rating") or {}).get("value") or 0)
        q = (p.get("q") or "").strip().lower()
        mode = p.get("mode") or "all"
        sel = {g: [v for v in (p.get(g) or "").split("|") if v] for g in self.GROUPS}
        maxtime = int(p["maxtime"]) if (p.get("maxtime") or "").isdigit() else None
        with_ = [w.strip().lower() for w in (p.get("with") or "").split(",") if w.strip()]
        without = [w.strip().lower() for w in (p.get("without") or "").split(",") if w.strip()]
        offset, limit = int(p.get("offset") or 0), int(p.get("limit") or 48)
        sort = p.get("sort") or "relevance"

        with self.lock:
            books_pool = [self.recipes[i] for i in self.order]
        pool = {"books": books_pool, "web": list(web_recipes)}.get(mode, books_pool + list(web_recipes))
        filtering = any(sel.values()) or maxtime or with_ or without or minrating
        if not q and not filtering:
            return {"results": [], "total": 0, "facets": {}}

        def vals(r, g):
            if g == "book":
                return [r.get("book") or "web:" + (r.get("site") or "web")]
            if g == "tag":
                return tags.get(r["id"], [])
            return r["_f"].get(g) or []

        def passes(r, skip=None):
            for g, how in self.GROUPS.items():
                if g == skip or not sel[g]:
                    continue
                v = vals(r, g)
                if how == "or" and not any(x in v for x in sel[g]):
                    return False
                if how == "and" and not all(x in v for x in sel[g]):
                    return False
            if skip != "time" and maxtime and not (r["_f"]["minutes"] and r["_f"]["minutes"] <= maxtime):
                return False
            if skip != "rating" and minrating:
                if minrating == "mine" and r["id"] not in my_ratings:
                    return False
                if minrating != "mine" and rating_of(r) < float(minrating):
                    return False
            if with_ and not all(w in r["_i"] for w in with_):
                return False
            if without and any(w in r["_i"] or w in r["_t"] for w in without):
                return False
            return True

        # text relevance (or pantry matching) first
        scored = []
        if mode == "pantry":
            items = [s.strip() for s in re.split(r"[,;\n]+", q) if s.strip()]
            for r in pool:
                hits = [it for it in items if it in r["_i"]]
                if hits:
                    in_title = sum(it in r["_t"] for it in items)
                    scored.append((len(hits) * 100 + in_title * 60 - r["_f"]["nIng"], r, {"matched": hits, "of": len(items)}))
        elif q:
            tokens = [t for t in re.split(r"[\s,]+", q) if t]
            for r in pool:
                tg = " ".join(tags.get(r["id"], [])).lower()
                fl = " ".join(r["_f"]["course"] + r["_f"]["protein"] + r["_f"]["diet"] + r["_f"]["method"]).lower()
                score = 0
                for t in tokens:
                    if t in r["_t"]:
                        score += 12 if re.search(r"\b" + re.escape(t), r["_t"]) else 6
                    elif t in tg:
                        score += 8
                    elif t in r["_i"]:
                        score += 3
                    elif t in fl:
                        score += 2
                    elif t in r["_b"]:
                        score += 1
                    else:
                        score = -1
                        break
                if score > 0:
                    if q in r["_t"]:
                        score += 15
                    scored.append((score, r, None))
        else:
            scored = [(0, r, None) for r in pool]

        matched = [x for x in scored if passes(x[1])]
        # facet counts: each group counted with every *other* filter applied
        facets = {}
        for g in self.GROUPS:
            c = {}
            for _, r, _ in scored:
                if passes(r, skip=g):
                    for v in vals(r, g):
                        c[v] = c.get(v, 0) + 1
            facets[g] = c
        tc = {}
        for _, r, _ in scored:
            m = r["_f"]["minutes"]
            if m and passes(r, skip="time"):
                for bkt in self.TIME_BUCKETS:
                    if m <= bkt:
                        tc[str(bkt)] = tc.get(str(bkt), 0) + 1
        facets["time"] = tc
        rc = {}
        for _, r, _ in scored:
            if passes(r, skip="rating"):
                v = rating_of(r)
                for th in ("3", "4", "4.5"):
                    if v >= float(th):
                        rc[th] = rc.get(th, 0) + 1
                if r["id"] in my_ratings:
                    rc["mine"] = rc.get("mine", 0) + 1
        facets["rating"] = rc
        facets["book"] = {k: {"n": n, "title": (self.books.get(k) or {}).get("title") or k.replace("web:", "")}
                          for k, n in facets["book"].items()}

        if sort == "time":
            matched.sort(key=lambda x: (x[1]["_f"]["minutes"] or 10**6, -x[0]))
        elif sort == "ingredients":
            matched.sort(key=lambda x: (x[1]["_f"]["nIng"], -x[0]))
        elif sort == "rating":
            matched.sort(key=lambda x: (-rating_of(x[1]), -x[0]))
        elif sort == "title":
            matched.sort(key=lambda x: x[1]["_t"])
        elif sort == "random":
            import random
            random.shuffle(matched)
        elif q or mode == "pantry":
            matched.sort(key=lambda x: (-x[0], len(x[1]["_t"])))
        else:
            matched.sort(key=lambda x: x[1]["_t"])
        page = matched[offset:offset + limit]
        res = []
        for _, r, extra in page:
            c = self.card(r, extra, tags)
            if r["id"] in my_ratings:
                c["myRating"] = my_ratings[r["id"]]
            res.append(c)
        return {"results": res, "total": len(matched), "facets": facets}

    def card(self, r, extra=None, tags=None):
        f = r.get("_f") or {}
        c = {"id": r["id"], "title": r["title"], "source": r.get("source", "book"),
             "snippet": ", ".join(i["t"] for i in r["ingredients"][:5] if not i.get("h"))[:160],
             "minutes": f.get("minutes"), "est": f.get("minutesEst"), "tags": (tags or {}).get(r["id"], [])}
        if r.get("source") == "book":
            b = self.books.get(r["book"], {})
            c.update(book=r["book"], bookTitle=b.get("title"), cover=f"/api/cover/{r['book']}" if b.get("cover") else None,
                     image=f"/api/img/{r['book']}?w=320&p={urllib.parse.quote(r['images'][0])}" if r.get("images") else None)
        else:
            rt = r.get("rating") or {}
            c.update(site=r.get("site"), image=r.get("image"), author=r.get("author"),
                     rating=rt.get("value"), ratingCount=rt.get("count"))
        if extra:
            c.update(extra)
        return c

    def recipe(self, rid):
        with self.lock:
            r = self.recipes.get(rid)
            if not r:
                return None
            b = self.books[r["book"]]
        out = {k: v for k, v in r.items() if not k.startswith("_")}
        out["facets"] = r["_f"]
        out["images"] = [f"/api/img/{b['id']}?w=900&p={urllib.parse.quote(p)}" for p in r["images"]]
        out["bookInfo"] = {"id": b["id"], "title": b["title"], "author": b["author"],
                           "cover": f"/api/cover/{b['id']}" if b.get("cover") else None}
        return out

    def library(self):
        with self.lock:
            books = [{"id": b["id"], "title": b["title"], "author": b["author"], "count": b["count"],
                      "cover": f"/api/cover/{b['id']}" if b.get("cover") else None} for b in self.books.values()]
            return {"books": books, "recipes": len(self.order), "status": self.status, "problems": self.problems,
                    "folders": self.cfg["library_folders"]}

    def random(self, n=6):
        import random
        with self.lock:
            ids = random.sample(self.order, min(n, len(self.order)))
        return [self.card(self.recipes[i]) for i in ids]


_EPUBS, _EPUB_LOCK = {}, threading.Lock()


def epub_for(book):
    """Keep books open between image requests — re-opening a 400 MB EPUB on Drive is slow."""
    with _EPUB_LOCK:
        ep = _EPUBS.get(book["epub"])
        if ep is None:
            ep = _EPUBS[book["epub"]] = extract.Epub(book["epub"])
        return ep


def _friendly_error(e):
    s = str(e)
    if isinstance(e, OSError) and e.errno in (5, 60, 89):
        return "Couldn't read the file (cloud drive didn't download it)"
    if "not a zip file" in s.lower():
        return "Couldn't read the file (cloud drive didn't download it, or it's not a real EPUB)"
    return s[:120]


# ------------------------------------------------------------------ state (favourites, list, plan, saved web recipes)

class State:
    def __init__(self):
        os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
        self.lock = threading.Lock()
        self.data = {}
        if os.path.exists(STATE_PATH):
            try:
                with open(STATE_PATH) as f:
                    self.data = json.load(f)
            except Exception:
                shutil.copy(STATE_PATH, STATE_PATH + ".corrupt")
        self.data.setdefault("web", {})

    def save(self, data):
        with self.lock:
            web = self.data.get("web", {})   # saved web recipes are owned by the server (import endpoint)
            self.data = data
            self.data["web"] = web
            tmp = STATE_PATH + ".tmp"
            with open(tmp, "w") as f:
                json.dump(self.data, f, ensure_ascii=False)
            os.replace(tmp, STATE_PATH)

    def add_web(self, rec):
        with self.lock:
            self.data.setdefault("web", {})[rec["id"]] = rec
            data = self.data
        self.save(data)

    def web_recipes(self):
        out = []
        for r in self.data.get("web", {}).values():
            r = dict(r)
            r["_t"] = r["title"].lower()
            r["_i"] = " | ".join(i["t"] for i in r["ingredients"] if not i.get("h")).lower()
            r["_b"] = (r.get("site") or "").lower()
            r["_f"] = facets.compute(r, r.get("site") or "")
            out.append(r)
        return out


# ------------------------------------------------------------------ HTTP

CTYPES = {".html": "text/html; charset=utf-8", ".js": "application/javascript; charset=utf-8",
          ".css": "text/css; charset=utf-8", ".svg": "image/svg+xml", ".png": "image/png",
          ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif", ".webp": "image/webp",
          ".json": "application/json", ".ico": "image/x-icon", ".webmanifest": "application/manifest+json"}


class Handler(BaseHTTPRequestHandler):
    lib: Library = None
    state: State = None
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        pass

    def _send(self, code, body, ctype="application/json", cache=None):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False).encode()
        elif isinstance(body, str):
            body = body.encode()
        if len(body) > 2048 and "gzip" in self.headers.get("Accept-Encoding", "") and not ctype.startswith("image/"):
            body = gzip.compress(body, 5)
            gz = True
        else:
            gz = False
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        if gz:
            self.send_header("Content-Encoding", "gzip")
        self.send_header("Cache-Control", cache or "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json_body(self):
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}")

    def do_GET(self):
        try:
            self._get()
        except Exception as e:
            traceback.print_exc()
            self._send(500, {"error": str(e)})

    def do_POST(self):
        try:
            self._post()
        except Exception as e:
            traceback.print_exc()
            self._send(500, {"error": str(e)})

    do_PUT = do_POST

    def _get(self):
        u = urllib.parse.urlparse(self.path)
        qs = {k: v[0] for k, v in urllib.parse.parse_qs(u.query).items()}
        p = u.path
        if p == "/api/library":
            return self._send(200, self.lib.library())
        if p == "/api/search":
            if qs.get("book") and not qs.get("q") and "limit" not in qs:
                qs["limit"] = "3000"
            res = self.lib.search(qs, web_recipes=self.state.web_recipes(), tags=self.state.data.get("tags") or {},
                                  my_ratings=self.state.data.get("ratings") or {})
            return self._send(200, res)
        if p == "/api/random":
            return self._send(200, {"results": self.lib.random(int(qs.get("n", 6)))})
        if p.startswith("/api/recipe/"):
            rid = urllib.parse.unquote(p.split("/", 3)[3])
            r = self.state.data.get("web", {}).get(rid) if rid.startswith("w-") else self.lib.recipe(rid)
            if r and rid.startswith("w-"):
                broken = any(st.get("t") in ("@type", "text", "url", "name", "image", "position") for st in r.get("steps", []))
                if broken and r.get("url"):
                    try:                       # saved before the NYT nested-step fix: re-import now
                        r = web.import_recipe(r["url"])
                        self.state.add_web(r)
                    except Exception:
                        pass
                elif "rating" not in r and r.get("url"):
                    threading.Thread(target=self._refresh_web, args=(r["url"],), daemon=True).start()
                r = dict(r, facets=facets.compute(r, r.get("site") or ""))
            return self._send(200, r) if r else self._send(404, {"error": "not found"})
        if p.startswith("/api/cover/"):
            b = self.lib.books.get(p.rsplit("/", 1)[1])
            if not b or not b.get("cover"):
                return self._send(404, b"", "text/plain")
            fp = os.path.join(CACHE, "covers", b["cover"])
            with open(fp, "rb") as f:
                return self._send(200, f.read(), CTYPES.get(os.path.splitext(fp)[1], "image/jpeg"), "max-age=86400")
        if p.startswith("/api/img/"):
            b = self.lib.books.get(p.rsplit("/", 1)[1])
            src = qs.get("p", "")
            if not b:
                return self._send(404, b"", "text/plain")
            w = int(qs["w"]) if qs.get("w", "").isdigit() else 0
            if w:
                thumb = os.path.join(CACHE, "thumbs", hashlib.sha1(f"{b['id']}|{src}|{w}".encode()).hexdigest() + ".jpg")
                if not os.path.exists(thumb):
                    os.makedirs(os.path.dirname(thumb), exist_ok=True)
                    tmp = thumb + ".src"
                    with open(tmp, "wb") as f:
                        f.write(epub_for(b).read_bytes(src))
                    subprocess.run(["sips", "-Z", str(w), "-s", "format", "jpeg", "-s", "formatOptions", "75", tmp, "--out", thumb],
                                   capture_output=True, timeout=60)
                    os.remove(tmp)
                if os.path.exists(thumb):
                    with open(thumb, "rb") as f:
                        return self._send(200, f.read(), "image/jpeg", "max-age=604800")
            data = epub_for(b).read_bytes(src)
            return self._send(200, data, CTYPES.get(os.path.splitext(src)[1].lower(), "image/jpeg"), "max-age=86400")
        if p == "/api/state":
            return self._send(200, {k: v for k, v in self.state.data.items() if k != "web"})
        if p == "/api/web/search":
            site, q = qs.get("site", "nyt"), qs.get("q", "")
            res = web.search_nyt(q) if site == "nyt" else web.search_eatingwell(q)
            return self._send(200, {"results": res})
        if p == "/api/info":
            return self._send(200, {"lan": lan_urls(self.server.server_address[1]) if LAN else []})
        # static files
        fp = os.path.normpath(os.path.join(STATIC, p.lstrip("/") or "index.html"))
        if not fp.startswith(STATIC) or not os.path.isfile(fp):
            fp = os.path.join(STATIC, "index.html")
        with open(fp, "rb") as f:
            self._send(200, f.read(), CTYPES.get(os.path.splitext(fp)[1], "application/octet-stream"))

    def _refresh_web(self, url):
        try:
            self.state.add_web(web.import_recipe(url))
        except Exception:
            pass

    def _post(self):
        p = urllib.parse.urlparse(self.path).path
        if p == "/api/state":
            self.state.save(self._json_body())
            return self._send(200, {"ok": True})
        if p == "/api/web/import":
            body = self._json_body()
            try:
                rec = web.import_recipe(body.get("url"), body.get("ld"))
            except web.Blocked as e:
                return self._send(200, {"blocked": True, "site": e.site, "url": body.get("url")})
            except Exception as e:
                return self._send(200, {"error": str(e)})
            self.state.add_web(rec)
            return self._send(200, rec)
        if p == "/api/reindex":
            if self.lib.status.get("state") != "indexing":
                if self._json_body().get("full"):
                    shutil.rmtree(os.path.join(CACHE, "books"), ignore_errors=True)
                    os.makedirs(os.path.join(CACHE, "books"), exist_ok=True)
                self.lib.cfg = load_config()
                self.lib.start()
            return self._send(200, {"ok": True})
        self._send(404, {"error": "not found"})


def lan_urls(port):
    urls = []
    try:
        host = socket.gethostname()
        if not host.endswith(".local"):
            host += ".local"
        urls.append(f"http://{host}:{port}")
    except Exception:
        pass
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        urls.append(f"http://{s.getsockname()[0]}:{port}")
        s.close()
    except Exception:
        pass
    return urls


LAN = "--lan" in sys.argv

if __name__ == "__main__":
    cfg = load_config()
    lib = Library(cfg)
    Handler.lib = lib
    Handler.state = State()
    lib.start()

    def backfill_ratings():       # recipes saved before ratings existed
        for r in list(Handler.state.data.get("web", {}).values()):
            if "rating" not in r and r.get("url"):
                try:
                    Handler.state.add_web(web.import_recipe(r["url"]))
                except Exception:
                    pass
    threading.Thread(target=backfill_ratings, daemon=True).start()
    host = "0.0.0.0" if LAN else "127.0.0.1"
    port = int(os.environ.get("PORT") or cfg["port"])   # PORT lets a launcher (e.g. the preview tool) pick the port
    srv = ThreadingHTTPServer((host, port), Handler)
    print(f"\n  Miso is running →  http://localhost:{port}")
    if LAN:
        for u in lan_urls(port):
            print(f"  On your iPad/phone →  {u}")
    print("  (Ctrl+C to stop)\n")
    if "--open" in sys.argv:
        subprocess.Popen(["open", f"http://localhost:{port}"])
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
