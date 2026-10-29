"""Run with: python3 -m unittest discover -s tests -v   (from the tricity-fetcher folder)"""
import functools
import http.server
import json
import os
import shutil
import sys
import tempfile
import threading
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import export  # noqa: E402
import fetcher  # noqa: E402
from sources import docs, hrera  # noqa: E402
from sources.base import find_date  # noqa: E402
from store import Store  # noqa: E402

FIX = os.path.join(HERE, "fixtures")
os.environ["no_proxy"] = os.environ["NO_PROXY"] = "127.0.0.1,localhost"  # keep local test traffic off any proxy


def read(name):
    with open(os.path.join(FIX, name), encoding="utf-8") as f:
        return f.read()


class Parsers(unittest.TestCase):
    def test_agents(self):
        rows = hrera.parse_agents(read("hrera_agents_pkl.html"))
        self.assertEqual(len(rows), 24)
        a = rows[0]
        self.assertEqual(a["reg_no"], "HRERA-PKL-REA-1247-2022")
        self.assertEqual(a["name"], "RAJAT KAUSHIK")
        self.assertEqual(a["district"], "Ambala")
        self.assertEqual((a["issued"], a["expires"]), ("2022-11-04", "2027-11-03"))
        self.assertTrue(a["certificate_url"].endswith(".pdf"))
        self.assertEqual(len({r["key"] for r in rows}), 24)

    def test_projects(self):
        rows = hrera.parse_projects(read("hrera_projects_pkl.html"))
        self.assertEqual(len(rows), 24)
        p = rows[0]
        self.assertEqual(p["project_id"], "RERA-PKL-589-2019")
        self.assertEqual(p["portal_id"], 681)
        self.assertEqual(p["registration_no"], "211 OF 2017 DATED 18.09.2017")
        self.assertEqual(p["registered_on"], "2017-09-18")
        self.assertEqual(p["location"], "KANWALA. SECTOR 27, AMBALA, HARYANA")  # the site splits words with <br>
        self.assertEqual(p["valid_upto"], "2024-09-17")
        self.assertFalse(p["lapsed"])
        lapsed = [r for r in rows if r["lapsed"]]
        self.assertTrue(lapsed)
        self.assertNotIn("Lapsed", lapsed[0]["registration_no"])
        self.assertTrue(all(r["detail_url"].startswith("https://haryanarera.gov.in/view_project/searchprojectDetail/") for r in rows))

    def test_changed_layout_is_an_error_not_an_empty_list(self):
        with self.assertRaises(ValueError):
            hrera.parse_projects("<table><tr><th>Something else</th></tr></table>")

    def test_dates(self):
        for text, want in [("08.02.2018", "2018-02-08"), ("dated 8-2-2018", "2018-02-08"), ("17/09/2024", "2024-09-17"),
                           ("2025-01-31", "2025-01-31"), ("04-Nov-2022", "2022-11-04"), ("Notice of 3 March 2026", "2026-03-03"),
                           ("no date", None), ("32.13.2020", None)]:
            self.assertEqual(find_date(text), want, text)

    def test_harvest(self):
        html = """<html><body><ul>
          <li><a href="/docs/aerocity-layout.pdf">Layout plan of Aerocity Block A to J</a> 12.05.2025</li>
          <li><a href="/en/e-auction-of-commercial-sites">E-auction of commercial sites, Sector 62</a> <span>03-10-2026</span></li>
          <li><a href="/en/rti">RTI</a></li>
          <li><a href="https://elsewhere.example/thing">Sector news elsewhere</a></li>
          <li><a href="https://cdn.example/plan_sector_66.pdf">Zoning plan sector 66</a></li>
          <li><a href="javascript:void(0)">Layout</a></li>
        </ul></body></html>"""
        found = docs.harvest(html, "https://gmada.gov.in/en/public-notices", docs.DEFAULT_KEYWORDS, ["gmada.gov.in"])
        urls = [f["url"] for f in found]
        self.assertEqual(urls, ["https://gmada.gov.in/docs/aerocity-layout.pdf", "https://gmada.gov.in/en/e-auction-of-commercial-sites",
                                "https://cdn.example/plan_sector_66.pdf"])
        self.assertEqual(found[0]["date"], "2025-05-12")
        self.assertEqual(found[1]["date"], "2026-10-03")
        self.assertEqual(found[0]["type"], "pdf")


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.s = Store(os.path.join(self.dir, "t.sqlite"))

    def tearDown(self):
        self.s.close()
        shutil.rmtree(self.dir)

    def test_lifecycle(self):
        self.assertEqual(self.s.upsert("x", "k", "1", {"a": 1}), "added")
        self.assertIsNone(self.s.upsert("x", "k", "1", {"a": 1}))
        self.assertEqual(self.s.upsert("x", "k", "1", {"a": 2}), "changed")
        self.s.upsert("x", "k", "2", {"a": 3})
        self.assertEqual(self.s.mark_missing("x", "k", ["1"]), 1)
        self.assertEqual([r["key"] for r in self.s.records("x", "k")], ["1"])
        self.assertEqual(self.s.upsert("x", "k", "2", {"a": 3}), "added")  # came back
        self.assertEqual([c["change"] for c in self.s.recent_changes(0)], ["added", "changed", "added", "removed", "added"])


class Handler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


class EndToEnd(unittest.TestCase):
    """Serves the fixtures over local HTTP and runs the real CLI against them."""

    @classmethod
    def setUpClass(cls):
        cls.web = tempfile.mkdtemp()
        shutil.copy(os.path.join(FIX, "hrera_agents_pkl.html"), os.path.join(cls.web, "agents.html"))
        shutil.copy(os.path.join(FIX, "hrera_projects_pkl.html"), os.path.join(cls.web, "projects.html"))
        with open(os.path.join(cls.web, "notices.html"), "w") as f:
            f.write('<ul><li><a href="/plan_sector_66.pdf">Zoning plan sector 66</a> 01.10.2026</li><li><a href="/private/x.pdf">Layout private</a></li></ul>')
        with open(os.path.join(cls.web, "plan_sector_66.pdf"), "wb") as f:
            f.write(b"%PDF-1.4 test")
        with open(os.path.join(cls.web, "robots.txt"), "w") as f:
            f.write("User-agent: *\nDisallow: /private/\n")
        cls.srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Handler, directory=cls.web))
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        base = "http://127.0.0.1:%d" % cls.srv.server_address[1]
        cls.work = tempfile.mkdtemp()
        cls.cfg = os.path.join(cls.work, "config.json")
        with open(cls.cfg, "w") as f:
            json.dump({"contact_email": "tests@localhost.invalid", "data_dir": os.path.join(cls.work, "data"), "min_delay_seconds": 0, "retries": 1,
                       "sources": {
                           "hrera": {"module": "hrera", "enabled": True, "publish": True, "export_districts": ["Panchkula"],
                                     "agents_url": base + "/agents.html", "projects_url": base + "/projects.html", "min_rows": 10},
                           "gmada": {"module": "docs", "enabled": True, "publish": False, "download": True, "pages": [base + "/notices.html"]}}}, f)

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        shutil.rmtree(cls.web)
        shutil.rmtree(cls.work)

    def cli(self, *args):
        fetcher.log.handlers.clear()
        return fetcher.main(["--config", self.cfg, "--quiet"] + list(args))

    def test_run_rerun_export(self):
        self.assertEqual(self.cli("run"), 0)
        st = Store(os.path.join(self.work, "data", "tricity.sqlite"))
        self.assertEqual(len(st.records("hrera", "agents")), 24)
        self.assertEqual(len(st.records("hrera", "projects")), 24)
        d = st.records("gmada", "documents")
        self.assertEqual([r["key"].rsplit("/", 1)[1] for r in d], ["plan_sector_66.pdf"])  # robots.txt kept /private/ out
        self.assertTrue(os.path.exists(os.path.join(self.work, "data", d[0]["data"]["file"])))
        first = len(st.recent_changes(0))
        st.close()

        # Second run: not due, so nothing fetched. A forced run of one source gets 304s and changes nothing.
        self.assertEqual(self.cli("run"), 0)
        self.assertEqual(self.cli("run", "--source", "hrera"), 0)
        st = Store(os.path.join(self.work, "data", "tricity.sqlite"))
        self.assertEqual(len(st.recent_changes(0)), first)
        st.close()

        # A project disappears and one changes.
        path = os.path.join(self.web, "projects.html")
        html = open(path).read()
        html = html.replace("RERA-PKL-1825-2025", "RERA-PKL-9999-2099").replace("ARCADIA INDUSTRIAL PARK", "ARCADIA PARK")
        html = html.replace("AFFORDABLE   PLOTTED  COLONY", "AFFORDABLE COLONY")
        open(path, "w").write(html)
        self.assertEqual(self.cli("run", "--source", "hrera", "--force"), 0)
        st = Store(os.path.join(self.work, "data", "tricity.sqlite"))
        new = [(c["change"], c["key"]) for c in st.recent_changes(0)][first:]
        st.close()
        self.assertIn(("added", "RERA-PKL-9999-2099"), new)
        self.assertIn(("removed", "RERA-PKL-1825-2025"), new)
        self.assertIn(("changed", "RERA-PKL-589-2019"), new)

        # Export: CSVs for both, site docs only for the publishable source, and only Panchkula rows.
        self.assertEqual(self.cli("export"), 0)
        out = os.path.join(self.work, "data", "export")
        self.assertTrue(os.path.exists(os.path.join(out, "gmada_documents.csv")))
        batch = json.load(open(os.path.join(out, "site_batch_1.json")))
        ids = [op["doc_id"] for op in batch]
        self.assertIn("index", ids)
        self.assertFalse(any(i.startswith("gmada") for i in ids))
        for op in batch:
            body = json.load(open(op["file_path"]))
            for it in body.get("items", []):
                self.assertEqual(it["district"], "Panchkula")
        self.assertTrue(os.path.exists(os.path.join(self.work, "data", "latest_changes.md")))

    def test_refuses_without_contact(self):
        cfg = json.load(open(self.cfg))
        cfg["contact_email"] = "you@example.com"
        p = os.path.join(self.work, "bad.json")
        json.dump(cfg, open(p, "w"))
        fetcher.log.handlers.clear()
        self.assertEqual(fetcher.main(["--config", p, "--quiet", "run"]), 2)


class Chunking(unittest.TestCase):
    def test_chunks_stay_under_limit(self):
        items = [{"n": i, "pad": "x" * 900} for i in range(1000)]
        parts = list(export.chunks(items, 100_000))
        self.assertEqual(sum(len(p) for p in parts), 1000)
        self.assertTrue(all(len(json.dumps(p)) < 110_000 for p in parts))


@unittest.skipUnless(os.environ.get("HRERA_FULL_PAGES"), "set HRERA_FULL_PAGES=<dir with hr_agents1.html, hr_projects1.html> to parse full saved pages")
class FullPages(unittest.TestCase):
    def test_full(self):
        d = os.environ["HRERA_FULL_PAGES"]
        agents = hrera.parse_agents(open(os.path.join(d, "hr_agents1.html"), encoding="utf-8", errors="replace").read())
        projects = hrera.parse_projects(open(os.path.join(d, "hr_projects1.html"), encoding="utf-8", errors="replace").read())
        print("\nfull pages: %d agents, %d projects, %d in Panchkula, %d lapsed" % (
            len(agents), len(projects), sum(p["district"] == "Panchkula" for p in projects), sum(p["lapsed"] for p in projects)))
        self.assertGreater(len(agents), 3900)
        self.assertEqual(len(projects), 1121)
        self.assertEqual(len({a["key"] for a in agents}), len(agents))


if __name__ == "__main__":
    unittest.main()
