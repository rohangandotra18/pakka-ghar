"""Shared plumbing for every source: a polite HTTP client and small HTML parsers.

Standard library only, so it runs on the Python 3 that ships with macOS.
"""
import email.utils
import gzip
import html
import os
import re
import socket
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
from html.parser import HTMLParser

VERSION = "0.1.0"


class FetchError(Exception):
    pass


class Response:
    def __init__(self, url, status, body, headers):
        self.url, self.status, self.body = url, status, body
        self.headers = {k.lower(): v for k, v in headers.items()}
        self.final_url = url

    @property
    def not_modified(self):
        return self.status == 304

    def text(self):
        ctype = self.headers.get("content-type", "")
        m = re.search(r"charset=([\w-]+)", ctype)
        return self.body.decode(m.group(1) if m else "utf-8", errors="replace")


def _ssl_context():
    bundle = os.environ.get("TRICITY_CA_BUNDLE")
    if bundle:
        return ssl.create_default_context(cafile=bundle)
    try:  # python.org builds on macOS often lack system certificates; certifi fixes that if installed
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


class Http:
    """One request at a time per host, robots.txt respected, retries with backoff, conditional GETs."""

    def __init__(self, cfg, store, log):
        email_addr = cfg.get("contact_email", "")
        if not email_addr or "example.com" in email_addr:
            raise FetchError("Set contact_email in config.json first. Site operators use it to reach you about the crawler.")
        self.ua = "TricityPropertyExchange-fetcher/%s (+mailto:%s)" % (VERSION, email_addr)
        self.delay = float(cfg.get("min_delay_seconds", 3))
        self.timeout = float(cfg.get("timeout_seconds", 60))
        self.retries = int(cfg.get("retries", 3))
        self.store, self.log = store, log
        self._last = {}
        self._robots = {}
        self._ctx = _ssl_context()

    def _host(self, url):
        return urllib.parse.urlsplit(url).netloc.lower()

    def allowed(self, url):
        host = self._host(url)
        if host not in self._robots:
            rp = urllib.robotparser.RobotFileParser()
            robots_url = "%s://%s/robots.txt" % (urllib.parse.urlsplit(url).scheme, host)
            try:
                resp = self._open(robots_url, conditional=False, check_robots=False, retries=1)
                rp.parse(resp.text().splitlines() if resp.status == 200 else [])
            except FetchError as e:
                self.log("robots.txt unavailable for %s (%s); treating as allowed" % (host, e))
                rp.parse([])
            self._robots[host] = rp
        return self._robots[host].can_fetch(self.ua, url)

    def _wait(self, host):
        gap = time.time() - self._last.get(host, 0)
        if gap < self.delay:
            time.sleep(self.delay - gap)
        self._last[host] = time.time()

    def get(self, url, conditional=True, max_bytes=None):
        """With conditional=True a 304 comes back when the page is unchanged since remember() was last called for it."""
        return self._open(url, conditional=conditional, max_bytes=max_bytes)

    def remember(self, resp):
        """Record validators only after the page was processed, so a failed parse is retried in full next time."""
        self.store.save_http_cache(resp.url, resp.headers.get("etag"), resp.headers.get("last-modified"))

    def _open(self, url, conditional=True, check_robots=True, retries=None, max_bytes=None):
        if check_robots and not self.allowed(url):
            raise FetchError("robots.txt disallows " + url)
        headers = {"User-Agent": self.ua, "Accept-Encoding": "gzip", "Accept-Language": "en-IN,en;q=0.8"}
        cached = self.store.http_cache(url) if conditional else None
        if cached:
            if cached.get("etag"):
                headers["If-None-Match"] = cached["etag"]
            if cached.get("last_modified"):
                headers["If-Modified-Since"] = cached["last_modified"]
        attempts = self.retries if retries is None else retries
        err = None
        for i in range(attempts):
            self._wait(self._host(url))
            try:
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=self.timeout, context=self._ctx) as r:
                    length = int(r.headers.get("Content-Length") or 0)
                    if max_bytes and length > max_bytes:
                        raise FetchError("%s is %d MB, over the %d MB limit" % (url, length // 1_000_000, max_bytes // 1_000_000))
                    body = r.read(max_bytes + 1 if max_bytes else -1)
                    if max_bytes and len(body) > max_bytes:
                        raise FetchError("%s is over the %d MB limit" % (url, max_bytes // 1_000_000))
                    if r.headers.get("Content-Encoding") == "gzip":
                        body = gzip.decompress(body)
                    resp = Response(url, r.status, body, dict(r.headers))
                    resp.final_url = r.geturl()
                return resp
            except urllib.error.HTTPError as e:
                if e.code == 304:
                    return Response(url, 304, b"", dict(e.headers))
                if e.code in (429, 500, 502, 503, 504):
                    err = FetchError("HTTP %d from %s" % (e.code, url))
                    retry_after = e.headers.get("Retry-After")
                    time.sleep(min(300, int(retry_after)) if retry_after and retry_after.isdigit() else 5 * 3 ** i)
                    continue
                raise FetchError("HTTP %d from %s" % (e.code, url))
            except (urllib.error.URLError, socket.timeout, ConnectionError, ssl.SSLError) as e:
                err = FetchError("%s: %s" % (url, getattr(e, "reason", e)))
                time.sleep(5 * 3 ** i)
        raise err or FetchError("failed: " + url)


def clean(s):
    return re.sub(r"\s+", " ", html.unescape(s or "")).strip()


class TableParser(HTMLParser):
    """Collects every table row as a list of cells; each cell keeps its text and links. Comments are ignored."""

    def __init__(self, base_url=""):
        super().__init__(convert_charrefs=True)
        self.base = base_url
        self.rows, self._row, self._cell = [], None, None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "tr":
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._cell = {"text": "", "links": [], "th": tag == "th"}
        elif tag == "a" and self._cell is not None and a.get("href"):
            self._cell["links"].append(urllib.parse.urljoin(self.base, a["href"].strip()))

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._cell is not None and self._row is not None:
            self._cell["text"] = clean(self._cell["text"])
            self._row.append(self._cell)
            self._cell = None
        elif tag == "tr" and self._row is not None:
            if self._row:
                self.rows.append(self._row)
            self._row = None

    def handle_data(self, data):
        if self._cell is not None:  # no added space: HRERA splits words with <br> ("H<br>ARYANA")
            self._cell["text"] += data


class LinkParser(HTMLParser):
    """Collects links with their text and the text of the enclosing row, list item or paragraph (for dates)."""

    BLOCKS = ("tr", "li", "p", "div", "article")

    def __init__(self, base_url=""):
        super().__init__(convert_charrefs=True)
        self.base, self.links, self._stack, self._a = base_url, [], [], None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in self.BLOCKS:
            self._stack.append({"tag": tag, "text": "", "links": []})
        if tag == "a" and a.get("href") and not a["href"].startswith(("#", "javascript:", "mailto:", "tel:")):
            self._a = {"url": urllib.parse.urljoin(self.base, a["href"].strip()), "text": "", "title": a.get("title", "")}

    def handle_endtag(self, tag):
        if tag == "a" and self._a is not None:
            self._a["text"] = clean(self._a["text"]) or clean(self._a["title"])
            if self._stack:
                self._stack[-1]["links"].append(self._a)
            else:
                self._a["context"] = self._a["text"]
                self.links.append(self._a)
            self._a = None
        elif tag in self.BLOCKS and self._stack and self._stack[-1]["tag"] == tag:
            blk = self._stack.pop()
            ctx = clean(blk["text"])
            for l in blk["links"]:
                l.setdefault("context", ctx)
                self.links.append(l)
            if self._stack:
                self._stack[-1]["text"] += " " + blk["text"]

    def handle_data(self, data):
        if self._a is not None:
            self._a["text"] += data
        if self._stack:
            self._stack[-1]["text"] += data


MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


def find_date(text):
    """First date in text as YYYY-MM-DD. Handles 08.02.2018, 08-02-2018, 08/02/2018, 2018-02-08, 8 Feb 2018 and 04-Nov-2022."""
    t = text or ""
    m = re.search(r"\b(20\d\d)-(\d\d)-(\d\d)\b", t)
    if m:
        return "%s-%s-%s" % m.groups()
    m = re.search(r"\b(\d{1,2})[./-](\d{1,2})[./-]((?:19|20)\d\d)\b", t)
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if 1 <= mo <= 12 and 1 <= d <= 31:
            return "%04d-%02d-%02d" % (y, mo, d)
    m = re.search(r"\b(\d{1,2})[\s-]+([A-Za-z]{3})[a-z]*[\s,-]+((?:19|20)\d\d)\b", t)
    if m and m.group(2).lower() in MONTHS:
        return "%04d-%02d-%02d" % (int(m.group(3)), MONTHS[m.group(2).lower()], int(m.group(1)))
    return None


def http_date(ts):
    return email.utils.formatdate(ts, usegmt=True)
