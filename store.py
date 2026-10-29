"""SQLite change store: what each source returned, when it first and last appeared, and what changed."""
import hashlib
import json
import sqlite3
import time

SCHEMA = """
CREATE TABLE IF NOT EXISTS records (
  source TEXT, kind TEXT, key TEXT, hash TEXT, data TEXT,
  first_seen REAL, last_seen REAL, changed_at REAL, removed_at REAL,
  PRIMARY KEY (source, kind, key));
CREATE TABLE IF NOT EXISTS changes (
  id INTEGER PRIMARY KEY AUTOINCREMENT, at REAL, source TEXT, kind TEXT, key TEXT,
  change TEXT, summary TEXT);
CREATE TABLE IF NOT EXISTS runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT, source TEXT, started REAL, finished REAL,
  status TEXT, added INTEGER, changed INTEGER, removed INTEGER, message TEXT);
CREATE TABLE IF NOT EXISTS http_cache (url TEXT PRIMARY KEY, etag TEXT, last_modified TEXT, at REAL);
CREATE INDEX IF NOT EXISTS changes_at ON changes(at);
"""


def digest(data):
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


class Store:
    def __init__(self, path):
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)

    def close(self):
        self.db.commit()
        self.db.close()

    # ---- records -------------------------------------------------------
    def upsert(self, source, kind, key, data, summary=""):
        """Returns 'added', 'changed' or None (unchanged). A record that had gone missing and returns counts as added."""
        now, h = time.time(), digest(data)
        row = self.db.execute("SELECT hash, removed_at FROM records WHERE source=? AND kind=? AND key=?", (source, kind, key)).fetchone()
        blob = json.dumps(data, ensure_ascii=False)
        if row is None or row["removed_at"]:
            self.db.execute("INSERT OR REPLACE INTO records VALUES (?,?,?,?,?,?,?,?,NULL)", (source, kind, key, h, blob, now, now, now))
            change = "added"
        elif row["hash"] != h:
            self.db.execute("UPDATE records SET hash=?, data=?, last_seen=?, changed_at=? WHERE source=? AND kind=? AND key=?",
                            (h, blob, now, now, source, kind, key))
            change = "changed"
        else:
            self.db.execute("UPDATE records SET last_seen=? WHERE source=? AND kind=? AND key=?", (now, source, kind, key))
            return None
        self.db.execute("INSERT INTO changes (at, source, kind, key, change, summary) VALUES (?,?,?,?,?,?)", (now, source, kind, key, change, summary))
        return change

    def mark_missing(self, source, kind, seen_keys, summary_of=lambda d: ""):
        """Call only after a complete listing: anything not seen this time is marked removed."""
        now, n = time.time(), 0
        seen = set(seen_keys)
        for row in self.db.execute("SELECT key, data FROM records WHERE source=? AND kind=? AND removed_at IS NULL", (source, kind)).fetchall():
            if row["key"] not in seen:
                self.db.execute("UPDATE records SET removed_at=? WHERE source=? AND kind=? AND key=?", (now, source, kind, row["key"]))
                self.db.execute("INSERT INTO changes (at, source, kind, key, change, summary) VALUES (?,?,?,?,?,?)",
                                (now, source, kind, row["key"], "removed", summary_of(json.loads(row["data"]))))
                n += 1
        return n

    def records(self, source, kind, include_removed=False):
        q = "SELECT * FROM records WHERE source=? AND kind=?" + ("" if include_removed else " AND removed_at IS NULL") + " ORDER BY key"
        return [dict(r, data=json.loads(r["data"])) for r in self.db.execute(q, (source, kind))]

    def get(self, source, kind, key):
        r = self.db.execute("SELECT data FROM records WHERE source=? AND kind=? AND key=?", (source, kind, key)).fetchone()
        return json.loads(r["data"]) if r else None

    def counts(self):
        return [dict(r) for r in self.db.execute(
            "SELECT source, kind, COUNT(*) AS live, MAX(last_seen) AS last_seen FROM records WHERE removed_at IS NULL GROUP BY source, kind ORDER BY source, kind")]

    def recent_changes(self, since):
        return [dict(r) for r in self.db.execute("SELECT * FROM changes WHERE at>=? ORDER BY at", (since,))]

    # ---- runs ----------------------------------------------------------
    def start_run(self, source):
        cur = self.db.execute("INSERT INTO runs (source, started, status) VALUES (?,?,?)", (source, time.time(), "running"))
        self.db.commit()
        return cur.lastrowid

    def finish_run(self, run_id, status, added=0, changed=0, removed=0, message=""):
        self.db.execute("UPDATE runs SET finished=?, status=?, added=?, changed=?, removed=?, message=? WHERE id=?",
                        (time.time(), status, added, changed, removed, message[:2000], run_id))
        self.db.commit()

    def last_runs(self):
        return [dict(r) for r in self.db.execute(
            "SELECT r.* FROM runs r JOIN (SELECT source, MAX(id) AS id FROM runs GROUP BY source) m ON r.id=m.id ORDER BY r.source")]

    def last_success(self, source):
        r = self.db.execute("SELECT MAX(finished) FROM runs WHERE source=? AND status='ok'", (source,)).fetchone()
        return r[0] or 0

    # ---- conditional GET cache -----------------------------------------
    def http_cache(self, url):
        r = self.db.execute("SELECT etag, last_modified FROM http_cache WHERE url=?", (url,)).fetchone()
        return dict(r) if r else None

    def save_http_cache(self, url, etag, last_modified):
        if etag or last_modified:
            self.db.execute("INSERT OR REPLACE INTO http_cache VALUES (?,?,?,?)", (url, etag, last_modified, time.time()))

    def forget_http_cache(self, url):
        self.db.execute("DELETE FROM http_cache WHERE url=?", (url,))
