# Pakka Ghar architecture

Pakka Ghar follows the AP2B blueprint (v0.2) for the backend and keeps Expo for the apps. This file says what runs
where, what the blueprint's rules look like in this code, and where it deliberately differs.

## The pieces

| Part | What it is | Where |
|---|---|---|
| Apps and website | Expo SDK 58 / React Native, one codebase: identical on iOS and Android, and the same screens on the web (react-native-web) | `src/` |
| API | Django 5.2 + Django Ninja, Python 3.12 | `backend/` |
| Database | PostgreSQL 16, the only store of record | `backend/apps/*/models.py` |
| Contract | OpenAPI 3.1, generated from the API; the app's TypeScript types come from it | `contracts/openapi.json`, `src/core/api/schema.d.ts` |
| Jobs | Celery + Redis (hold expiry, monthly rent, settlements); inline when `REDIS_URL` is unset | `backend/config/celery.py`, `apps/*/tasks.py` |
| Live events | Server-sent events, one per notification | `GET /api/events`, `src/core/api/events.tsx` |

Backend apps: `core` (organisations, people, ledger, audit, idempotency, notifications, CORS for the website),
`identity` (OTP sign-in, session tokens, DigiLocker), `property` (PGs, rooms, beds, meters, papers, payouts, on-site
photos), `booking` (applications with roommates, room bids, tours, holds, bookings, agreements and e-signatures,
police verification, ratings), `payments` (invoices, payments, webhooks, electricity),
`maintenance` (repairs and trust reports), `jurisdiction` (Tricity police and tariff rules), and the trust team's
review queue (`apps/core/staff_api.py`).

## Where code lives

The code is organised by feature, so a change to one feature, or to the design, stays in one folder. The rules are
checked by `npx expo lint` (`eslint.config.js`): a file that reaches past them fails the lint.

**App (`src/`)**

| Folder | What's in it | May use |
|---|---|---|
| `design/` | The look: colours, type, spacing (`theme.ts`), fonts (`fonts.ts`), icons and every drawn element (`ui.tsx`: Screen, Btn, Card, Field, Toast…), the tab bar, the loading state | nothing else in the app |
| `core/api/` | The typed API client (generated from the contract), `useQuery` / `useAction`, live events | `core/` only |
| `core/session/` | Who is signed in on this device, for each side; toasts; the refresh signal | `core/` only |
| `core/device/` | The on-site camera with location | `core/` only |
| `shared/` | Widgets several features use: the top bar with the tenant/owner switch, the sign-up prompt, the map | design, core |
| `features/<name>/` | One feature: its screens and parts, and an `index.ts` listing what other code may use | design, core, shared, other features' `index.ts` |
| `shell/` | The frame: providers and fonts, the stack, both tab bars, the toast host | everything, via `index.ts` |
| `app/` | The URL map for Expo Router. Each file is one line re-exporting a feature's screen | features, shell |

Features: `welcome`, `account` (tenant sign-up), `listing` (owner lists a PG), `search` (find and a listing's page),
`tours`, `applications` (requests to stay, roommates, bids), `booking`, `agreements`, `photos`, `stay` (My stay,
history, rating), `repairs`, `owner-dashboard` (Today, beds, money, residents).

What to change for what:

- **A redesign** (colours, type, buttons, cards, spacing, icons): `src/design/` only. Screens use its components
  and tokens, so they follow.
- **One feature**: its folder in `src/features/`. Other features see only what its `index.ts` exports, so you can
  rewrite its insides freely. If you change something it exports, lint and `tsc` show every user.
- **A new screen**: put it in its feature, export it from the feature's `index.ts`, and add a one-line route
  file in `src/app/`.
- **A URL**: rename the route file in `src/app/` and the `router.push` calls that use it. URLs are how features
  link to one another.

**Backend (`backend/apps/`)**

Each Django app is a domain: `core`, `identity`, `property` (listings, rooms, photos), `payments`, `maintenance`
(repairs), `jurisdiction` (police and tariff rules). `booking` is split by feature, with one package each for
`applications`, `tours`, `bookings`, `agreements`, `police`, `stay` and `owner_dashboard`. Each package has a `services.py`
(the rules) and an `api.py` and/or `owner_api.py` (its endpoints). `booking/common.py` holds the few shared
lookups. The models stay in each app's `models.py`, because that is the database schema and its migrations.
Splitting the code never changes tables or row-level security. Endpoints keep their URLs, and their OpenAPI
operation ids are the view's name, not its file, so moving code between files never changes the app's contract.

## One account on every device

An account is a phone number. The same person signs in with a code on an Android phone, an iPhone or the website
and sees the same records, because everything lives in Postgres and each device holds only a session token (the
phone's secure store, or the browser's local storage on the web). One person can be a tenant and an owner; the app
keeps a token for each side and the switch at the top changes sides. Signing in as an owner who already has a PG goes
straight to their dashboard. Each signed-in device is its own revocable session.

The website is the same Expo code built for the browser (`npx expo start --web`, or `npx expo export -p web` for a
static build). Tenants get Find, My stay, Requests and History; owners get Today, Beds, Money, Residents and Requests.
What differs on the web: the map draws MapLibre straight into the page (`src/shared/map/MapView.web.tsx`; phones run the same
engine in a web view), and photos can only be taken on a phone, because they must come from the phone's camera at the
building. The API allows the website's origin through `CORS_ORIGINS`.

In a browser window at least 900 px wide (`useWide()` in `src/design/`) the website gets a desktop layout; phones
and narrow windows are untouched, because every desktop branch sits behind that one test. The root layout draws a
site header (`src/shell/SiteHeader.tsx`: logo, page links, account menu) in place of the bottom tab bar; the owner
dashboard keeps its sidebar instead. `Screen` takes `width` (`text` 760 px, `wide` 1120 px, `full`), and `Columns`
gives a main column with a side panel that stays in view. The landing page (`src/features/welcome/`), Find (a
results pane beside a full-height map) and a PG's page (gallery, details and a booking panel) each have a wide
layout built from the same parts as the phone one. Browser-tab titles and the page description are set after the
page loads (`src/shell/DocumentHead.tsx`); the site is still a single-page app, so they are not in the first HTML
a crawler receives.

The map's behaviour is written once, in `src/shared/map/mapCore.js` (pins, clustering, the selected pin, the camera
rules, "the map moved" events). The website imports it; phones run a generated copy inside the web view, so after
editing it run `npm run map:engine` (it also runs on `npm install`), and `npm run test:map` checks it under plain
Node. Find (`src/features/search/`) searches around a chosen place or inside the map area on screen
(`GET /api/listings` with `lat`/`lng` or `bbox`, plus `gender`, `max_rent_paise`, `kind`), and its place search
reads `GET /api/places`, a public reference table loaded from `backend/apps/property/data/tricity_places.json`
by `manage.py load_places` (regenerate the file with `backend/scripts/fetch_places.py`).

## Photos and agreements

- **Photos** are taken in the app's camera only, with the phone's location at that moment. The server keeps a
  photo only if it was taken in the last 10 minutes within 150 m of the PG's pin, decodes as a real camera image, has
  no editing or AI-tool marks and isn't a duplicate. It is re-encoded without metadata (`apps/property/photos.py`).
- **Agreements** are the owner's own PDF behind a filled-in cover page, or the standard text. They sit in private
  storage and are never served as files. The app shows each page as an image through a signed link that names the
  agreement, page and copy and expires in 15 minutes. PDFium renders one page at a time, and pages are cached by the
  document's SHA-256. Signing needs every page opened, the typed name and a one-time code. Signatures are
  append-only. Once both have signed, a certificate page with both signatures and the document's SHA-256 is added
  (`apps/booking/agreements/`).

## The blueprint's first principles, in this code

1. **One source of truth.** Postgres holds every record. Listing availability, ratings and balances are computed
   from it on each read; nothing is cached in a second store. The app keeps only who is signed in.
2. **One contract.** `backend/manage.py export_openapi` writes the OpenAPI schema and `npm run api:types` regenerates
   the app's types from it, so an API change that breaks a screen fails `tsc`.
3. **One permission policy.** Row-level security is enabled and *forced* on every business table
   (`apps/core/rls.py`, the `000*_rls` migrations). Each request sets `app.current_org` and `app.current_party`;
   the database filters every query, including raw SQL. Work that spans owners (webhooks, scheduled jobs, public
   listing aggregates, the trust team) switches to the `pakka_system` role explicitly with `system()`. A cash report about
   an owner is invisible to that owner at the database level.
4. **One append-only ledger.** Money is integer paise. Every financial event is a balanced journal
   (`apps/core/ledger.py`); a trigger rejects any journal that doesn't sum to zero at commit, and triggers reject
   `UPDATE`/`DELETE` on journals, lines and the audit trail. Cancellations post contra-entries.
5. **Humans decide critical boundaries.** Owners accept applications and bids, confirm tours, sign agreements, submit police packets and mark
   them verified; the app never decides those on its own.
6. **Never green without evidence.** `backend/tests` runs against a real Postgres test database: cross-tenant
   isolation (AC-20), no double booking (AC-12), ledger rules (AC-16–18), idempotent replays, token revocation
   (AC-19), applications, roommates and the bid cap, tours, on-site photos, agreement signing, CORS, webhooks, metered electricity and a full stay.

## Deliberate differences from the blueprint

- **Expo instead of Next.js + Capacitor (ADR-004).** The apps are native, which keeps maps, gestures, keyboard
  handling and the identical-on-both-platforms design. The website is the same code through react-native-web, so
  there is one set of screens to keep right, not two.
- **Repository layout.** The Expo app stays at the root (its tooling expects that); the backend is in `backend/`
  with its own environment. Metro and TypeScript ignore `backend/`.
- **Double-booking constraint.** The exclusion constraint compares `int8range(bed_id, bed_id, '[]')` instead of
  `bed_id WITH =`. It means the same thing and needs no `btree_gist` extension (the local Postgres build lacks it).
  With `btree_gist` available in production, either form works.
- **Sign-in.** Phone OTP with revocable session tokens. WebAuthn passkeys (AC-01) need a development build with a
  native passkey module; they are the next step for sign-in.
- **No `/legacy/` ERP5 archive or prompt runbook.** This project never had an ERP5 codebase.
- **No cash, ever.** The blueprint's example command "Record cash payment" is not supported: there is no cash
  payment method, and a cash request can only be reported to the trust team.

## Personal data (DPDP Act, 2023)

- `GET /api/me/data` returns everything held about the caller, read under their own row-level security.
- `POST /api/me/delete` erases the account: name, phone, ID details, police-form details, notifications and sign-in
  codes go; bookings, invoices, payments, the ledger and ratings stay against an anonymous id, as tenancy, tax and
  payment records must be kept. It is refused while the person has a booking or stay, a deposit in escrow, an unpaid
  bill, or a PG they manage. VERIFY the retention periods with counsel.
- Aadhaar is never stored: only its last four digits, the DigiLocker reference and when it was checked.

## Money flow

Pakka Ghar never holds money. Deposits go to the payment partner's escrow account; rent settles from the partner to
the owner's bank. The ledger records the owner's side of each event:

| Event | Debit | Credit |
|---|---|---|
| Deposit captured | escrow | deposit owed to resident |
| Rent charged | resident owes | rent income |
| Electricity charged | resident owes | electricity recovered |
| Bill paid in the app | collected by partner | resident owes |
| Daily settlement | owner's bank | collected by partner |
| Deposit returned (less a deduction) | deposit owed to resident | escrow; deduction to owner's bank and income |

A payment becomes captured only through the partner's webhook (HMAC-checked, stored once per event id). In
development, `/api/dev/payments/{id}/capture` sends that same signed webhook through the real handler.

## Before launch: things that must be checked by a person

- **Police packet fields** for Chandigarh Police, Punjab Police (Mohali) and Haryana Police (Panchkula):
  `apps/jurisdiction/rules.py`.
- **Electricity tariff ceilings** per distribution company, from the current tariff orders: same file.
- **GST treatment** of PG rent (the exemption limit and the taxable rate above it): `apps/payments/services.py`,
  with a CA.
- **Providers.** OTP (SMS/WhatsApp), DigiLocker, Razorpay or Cashfree with escrow, and eSign/e-stamp all run as
  local fakes. Each has a single place to wire the real client (`apps/identity/services.py`,
  `apps/payments/services.py`, `apps/booking/bookings/services.py` for the e-stamp). With `DEBUG=0` the server
  refuses to start while `KYC_PROVIDER`, `PAYMENT_PROVIDER` or `OTP_PROVIDER` is still the fake, unless
  `ALLOW_FAKE_PROVIDERS=1` says it is a demo server.
- **Development stand-ins**: `/api/dev/payments/{id}/capture` (acting as the payment partner) and returning the OTP
  to the app exist only with `DEBUG=1`.

## Running it

```bash
cd backend
uv venv .venv --python 3.12 && uv pip install --python .venv/bin/python -r requirements.txt -r requirements-dev.txt
scripts/dev-db.sh                         # local Postgres 16 (first run creates roles and the database)
.venv/bin/python manage.py migrate
.venv/bin/python manage.py load_places    # sectors, colleges, hospitals and stations to search from (OpenStreetMap, ODbL)
.venv/bin/python manage.py make_staff "+91 XXXXX XXXXX"   # someone on the trust team, to approve new PGs
.venv/bin/python manage.py runserver 0.0.0.0:8000
.venv/bin/python -m pytest                # the test suite
```

In production, run the API with `gunicorn -c gunicorn.conf.py config.wsgi` (in `backend/`). It uses threaded
workers because every open app keeps a live-events stream for up to five minutes. Size `WEB_WORKERS` x
`WEB_THREADS` to the database's connection limit, and run Celery beat (with `REDIS_URL`) for hold expiry and
monthly bills. API traffic also releases lapsed holds, so free beds are right even if beat stops.

Then `npx expo start` at the root: press `i` for the iPhone simulator, `a` for Android, `w` for the website
(http://localhost:8081). The app finds the API on Metro's host at port 8000 (set `EXPO_PUBLIC_API_URL` to
override). For the Android emulator, also run `adb reverse tcp:8000 tcp:8000`.

The database starts empty: there is no sample data. An owner signs up in the app and lists a PG; it goes live once
someone on the trust team approves it on the Trust team screen (`/staff`, in the account menu for staff; it uses
`GET /api/staff/queue` and `POST /api/staff/properties/{id}/approve`). For development only,
`manage.py seed_demo` fills an empty database with demo PGs, residents, a trust-team queue and placeholder photos
marked "Demo photo", and prints the numbers to sign in with; it refuses to run without `DEBUG=1`. With
`DEBUG=1` the sign-in code is filled in for you, and `/api/dev/payments/{id}/capture` stands in for the payment
partner. `manage.py reset_data --yes` empties every table (development only).
