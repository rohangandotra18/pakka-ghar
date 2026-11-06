"""Production web server: `gunicorn -c gunicorn.conf.py config.wsgi`.

Each phone or browser with the app open keeps one live-events stream (GET /api/events) for up to five minutes,
then reconnects. With plain worker processes every open app would hold a whole worker; threads let one process
serve many streams and ordinary requests side by side. Each thread uses at most one database connection, so
workers x threads must stay under the database's connection limit (or put PgBouncer in front)."""
import multiprocessing
import os

bind = os.environ.get('BIND', '0.0.0.0:8000')
workers = int(os.environ.get('WEB_WORKERS', min(4, multiprocessing.cpu_count())))
worker_class = 'gthread'
threads = int(os.environ.get('WEB_THREADS', 32))
timeout = 330            # longer than one events stream (300 s), so a quiet stream is never killed as hung
graceful_timeout = 30
keepalive = 5
accesslog = '-'          # the app logs one line per request itself; gunicorn's access log goes to stdout too
max_requests = 2000      # recycle workers now and then
max_requests_jitter = 200
