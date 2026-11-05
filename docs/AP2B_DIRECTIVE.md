# AP2B / Pakka Ghar: delivery directive (consolidated)

This replaces the earlier "Master Full-Platform Scope" prompt. It keeps its intent (simple, trustworthy journeys
that actually work; honest status; no fake progress) and removes what contradicted the build or couldn't be executed.
Give it, with this repository, to any engineer or AI coding agent. `ARCHITECTURE.md` describes the system as built.

## 1. Decisions already made (do not reopen without the founder)

| Decision | Choice | Why |
|---|---|---|
| Business engine | **Django 5.2 + Django Ninja on PostgreSQL 16** (`backend/`). Not ERP5. | Blueprint ADR-001; integrity is enforced in the database (row-level security, append-only ledger, no double booking); widely known stack; working and tested. ERP5 may later be *integrated* for heavy back-office modules, never as the rental core. |
| Apps and website | **Expo / React Native**, one codebase: identical on iOS and Android, and the same screens on the web. One account (a phone number) works on every device. | Native maps, camera, gestures; one team; owners and tenants switch between Android, iPhone and a browser freely. |
| Contract | **OpenAPI 3.1** generated from the API (`contracts/openapi.json`); app types generated from it. | A breaking API change fails the app typecheck. |
| Product | **Pakka Ghar: PGs and rentals in the Chandigarh Tricity.** | Release one is the landlord ↔ tenant journey. |
| Money | **Free for everyone. No cash, ever.** The platform never holds money (payment partner + escrow). | Founder decision, 4 Nov 2026. Fees, commissions and ads are out of scope until the founder changes this. |
| Data | **No sample data.** The database starts empty. | Founder decision, 5 Nov 2026. |
| Photos | **Taken in the app's camera, at the building, just now.** No gallery, edited or AI images. | Founder decision, 5 Nov 2026. |
| Repository | Git; hosted at github.com/rohangandotra18/pakka-ghar (public). Push only when the founder asks. | Founder decision, 5 Nov 2026. |

## 2. Release one: the landlord ↔ tenant journey (scope and definition of done)

Release one is done when every item below is true **on a real phone, against the real database**, with an automated
test where one is possible. Status lives in §6, never in a separate plan.

Owner
1. Signs in with a mobile code; verifies identity (DigiLocker; last 4 Aadhaar digits only).
2. Lists a PG: details, city, exact building pin, rooms and beds with rent, ownership papers, payout account, no-cash promise.
3. Adds photos taken on site with the camera; anything else is refused.
4. Uploads their own agreement (PDF) or uses the standard one.
5. Is approved by the trust team before the PG is visible; sees the reason if sent back.
6. Sees requests to stay (alone or with roommates) with each person's verified ID and rental record; accepts or declines.
7. Can put a room up for sealed bids (rent to +15%) and stop; accepting the best bids fills the room.
8. Confirms or declines tour requests; sets tour hours.
9. Reads and countersigns each agreement (typed name + code); submits the police-verification packet.
10. Sees today's to-dos, the bed board, residents, money in and deposits in escrow; assigns repairs to their own contacts.

Tenant
11. Browses and searches without an account; sees the map, photos marked "taken on site", rooms with free beds and bids.
12. Signs up only when acting; gives the police-form details once.
13. Schedules a tour at one of the owner's free times; can cancel.
14. Applies alone or with up to two roommates (invited by phone, each verifies and joins in their own app); or bids on a room.
15. Once accepted, pays their own deposit into escrow within 24 hours.
16. Reads every page of the agreement and signs (typed name + code); both get the signed copy with a certificate page.
17. E-stamps; sees My stay: bill, meter, receipts, AutoPay, notice; raises repairs with a camera photo; reports cash requests to the trust team only.
18. Rates the stay; deposit is returned from escrow (less an explained deduction); history and rating carry to the next PG.

Everyone
0. Uses one account (their phone number) on Android, iPhone and the website, and sees the same records on each.
19. Can export their data and erase their account (refused while a stay, deposit, bill or PG is open).
20. No screen shows another person's or another owner's records (tested at the database).

## 3. Explicitly not in release one

Sale and purchase, developers and construction, hotels / B&B / short stay / OTAs, coworking, brokers and partner
marketplaces, influencers / affiliates / ads / subscriptions, digital locks, AI agents acting on accounts, Hindi and
Punjabi (planned next). Each needs its own scoped brief when it's chosen.

## 4. Must be settled by a person before launch (not by an AI)

- **Payments:** contract with Razorpay or Cashfree, escrow account for deposits, RBI payment-aggregator compliance; wire
  `apps/payments/services.py` (the dev capture stand-in is then disabled with `DEBUG=0`).
- **Identity:** DigiLocker partner access; OTP via SMS/WhatsApp provider (`apps/identity/services.py`).
- **Agreements:** whether OTP-confirmed signatures suffice or licensed Aadhaar eSign is required (IT Act 2000); stamp
  duty and registration rules in Chandigarh UT, Punjab (Mohali) and Haryana (Panchkula); the standard agreement text
  (`apps/booking/agreements.py`) reviewed by a lawyer.
- **Police forms** per city and **electricity tariff ceilings** per distribution company (`apps/jurisdiction/rules.py`).
- **Tax:** GST on PG rent; TDS on rent (194-IB) guidance for residents; owner statement wording.
- **Data protection (DPDP Act 2023):** consent notices, retention periods for kept financial records, grievance officer.
- **Hosting:** managed PostgreSQL with backups and a tested restore; object storage for photos; private storage for agreements.

## 5. How work is done

- One bounded task at a time, each with acceptance tests written first; no task is "done" without them passing.
- Backend: `cd backend && .venv/bin/python -m pytest` (real Postgres). App: `npx tsc --noEmit && npx expo lint`.
  After an API change: `manage.py export_openapi` then `npm run api:types`.
- Test on both an iOS simulator and an Android emulator (or devices) for any screen change.
- New tables get a row-level-security policy migration; the guard test fails otherwise.
- Never fabricate approvals, test results, screenshots or progress. An AI review is labelled as such; it is not a
  human sign-off. If something wasn't run, say so.
- Report: what works now (with the test or device evidence), what's in progress, what's blocked and on whom, next step.

## 6. Status (update in the same commit as the work)

| # | Item | Status | Evidence |
|---|---|---|---|
| 0 | One account on Android, iPhone and web | Built; tested on Android and web | same owner on both, 5 Nov; iPhone run pending (simulator access) |
| 1–2, 5 | Owner sign-up, listing, trust-team approval | Built, tested on Android | backend tests; device run 5 Nov |
| 3 | On-site camera photos | Built, tested on Android | `tests/test_applications.py`; photo taken 0 m from the pin, 5 Nov |
| 4, 9, 16 | Owner agreement upload; read and e-sign | Built, tested end to end | `tests/test_agreements.py`; owner PDF uploaded (Android), tenant signed (web), owner countersigned (Android), certificate page, 5 Nov |
| 6, 14 | Applications, roommates | Built, tested end to end | `tests/test_applications.py`; tenant applied with a roommate (web), roommate joined, owner accepted (Android), 5 Nov |
| 7 | Room bids | Built, backend tested | `tests/test_applications.py`; device run pending |
| 8, 13 | Tours | Built, tested end to end | tenant booked (web), owner confirmed (Android), 5 Nov |
| 10, 17, 18 | Dashboards, stay, repairs, move-out | Built, tested on iOS, Android and web | backend tests; device runs 5 Nov |
| 11–12 | Browse, search, map, sign-up | Built, tested on iOS, Android and web | device runs 5 Nov |
| 15 | Deposit into escrow | Built with a payment stand-in | paid on web, 5 Nov; real partner pending (§4) |
| 19–20 | Data export / erasure; isolation | Built, backend tested | `tests/test_privacy_visits.py`, `tests/test_rls.py`, signed page links in `tests/test_agreements.py` |
| §4 | Providers, legal, tax, hosting | Not started | needs people and contracts |
