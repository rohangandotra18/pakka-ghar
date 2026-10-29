# Tricity public-records fetcher

Runs on a Mac in India. Every hour it checks which sources are due, fetches them, records what is new, what changed and what disappeared, and shows a macOS notification when something moves. It uses only the Python 3 standard library and needs nothing installed beyond `python3`.

The Mac has to be in India because the GMADA, PUDA, HSVP, Chandigarh and Punjab RERA sites refuse connections from abroad, which includes cloud servers. Haryana RERA is reachable from anywhere.

## Sources

| id | What it collects | State |
|---|---|---|
| `hrera` | Haryana RERA, Panchkula bench: all registered agents (about 3,990) and registered projects (about 1,120, 45 in Panchkula district), with registration and expiry dates, lapsed status, and links to certificates and progress reports | Parser checked against the live pages on 29 Oct 2026 |
| `gmada` | GMADA public notices and zoning/layout plans; new PDFs are downloaded | URLs not yet confirmed: run a probe first |
| `puda` | PUDA zoning plans | Probe first |
| `hsvp` | HSVP (Panchkula) notices | Start page only; probe, then point it at the right pages |
| `chandigarh` | Chandigarh Administration and Chandigarh Housing Board notices | Start pages only; probe first |
| `punjab_rera` | Punjab RERA public pages | Probe first |
| `igr_punjab` | Punjab collector rates | Off by default; URL not confirmed |

The fetcher never:

- solves or works around a CAPTCHA (it skips the Haryana RERA and Punjab RERA project searches);
- logs in anywhere;
- fetches anything robots.txt disallows.

It makes one request at a time per site, at least 3 seconds apart. Its User-Agent carries your contact email so a site operator can reach you. When a site sends ETag or Last-Modified headers, it only downloads pages that changed.

BAANKNET is deliberately left out: its terms forbid reproducing its material on other sites or for commercial use. On the website, link out to its listings instead.

## Publishing: permission first

Every source starts with `"publish": false`. While it is false the data stays on the Mac, in the SQLite file and the CSVs, and is never included in the site import. Indian government sites usually say their material may be reproduced only with permission. Haryana RERA's terms, for example, say material "may be reproduced after taking proper permission by sending a mail", with the source acknowledged.

To publish a source:

1. Email the department, saying what you will show and how you will credit them.
2. Keep their reply.
3. Set `"publish": true` for that source in `config.local.json`.

The `attribution` text goes out with the exported data.

## Setup on the Mac

1. Put this folder somewhere outside Documents, Desktop, Downloads and iCloud Drive, for example `~/tricity-fetcher`. macOS blocks background jobs from reading those folders.
2. Run the installer:

   ```bash
   cd ~/tricity-fetcher
   ```

   ```bash
   ./scripts/install_mac.sh
   ```

   It asks for your contact email, writes `config.local.json`, runs the tests, installs the background job and starts the first run.
3. Probe the sources whose URLs are unconfirmed, then send the saved pages from `data/probe/` back so the page lists and keywords can be tuned:

   ```bash
   python3 fetcher.py run --source gmada --source puda --source hsvp --source chandigarh --source punjab_rera --probe
   ```

The job runs while you are logged in and the Mac is awake. To keep it running on a Mac that stays plugged in, open System Settings → Energy (or Battery → Options) and turn on "Prevent automatic sleeping when the display is off".

## Everyday commands

```bash
python3 fetcher.py status
```

```bash
python3 fetcher.py changes --days 7
```

```bash
python3 fetcher.py run --source hrera
```

```bash
python3 fetcher.py export
```

Use `--force` with `run` to ignore cached headers and refetch everything.

The fetcher writes these files:

- `data/tricity.sqlite`: every record with first-seen, last-seen, changed and removed times, plus a change log and run history.
- `data/latest_changes.md`: the last 7 days of changes, rewritten after each run.
- `data/docs/<source>/`: downloaded PDFs, named by hash so a replaced file is kept alongside the old one.
- `data/export/*.csv`: one CSV per source and kind, which opens in Numbers or Excel.
- `data/export/site_batch_*.json`: import batches for the website, built only from sources with `publish` set to true.
- `data/logs/fetcher.log`: the run log.

## Getting data onto the website

The website keeps shared data in its own database. `export` writes documents for a `ref` collection: compact, at most 200 KB each, and limited to Panchkula district for Haryana RERA. It also writes batch files of at most 50 writes each. To import them, open a Claude session that can reach this folder and ask it to import `data/export/site_batch_*.json` into the Tricity Property Exchange artifact.

Before the first import, the site needs two changes:

- a `ref` rule so viewers can read the collection and only editors can write it;
- a page that shows the data.

## Changing settings

Put overrides in `config.local.json`, which git ignores. It is merged over `config.json`, for example:

```json
{
  "contact_email": "you@yourdomain.in",
  "sources": {
    "gmada": { "pages": ["https://gmada.gov.in/en/public-notices", "https://gmada.gov.in/en/auctions"] },
    "hrera": { "publish": true }
  }
}
```

Each source accepts these settings:

- `enabled`
- `publish`
- `every_hours`
- `pages` and `hosts` (notice sources)
- `keywords`
- `download`
- `export_districts` (Haryana RERA)

## Tests

```bash
python3 -m unittest discover -s tests -v
```

The tests cover:

- the parsers, against saved Haryana RERA rows;
- date formats;
- link harvesting;
- the change store;
- an end-to-end run against a local web server, covering robots.txt, unchanged pages, additions, removals and export.

When a site changes its layout, the parser stops with an error rather than reporting every record as removed. A list that suddenly comes back much shorter is also treated as an error.
