# Pakka Ghar app

One React Native (Expo SDK 58) codebase for iOS and Android. It looks the same on both platforms because:

- every control is drawn by the app (tab bar, buttons, toggle, offer stepper, star input); there are no native switches, sliders or ripples
- Manrope and Bricolage Grotesque are bundled
- there are no platform shadows, only borders
- the slide animation is the same on both

Screens cover tenant and owner onboarding, offers on scarce beds, booking with escrow deposit, Aadhaar eSign and e-stamp, rent and electricity, requests (including "asked to pay in cash"), resident records, rental history and ratings. Every screen reads and writes through the API in `backend/` (Django + PostgreSQL); see [ARCHITECTURE.md](ARCHITECTURE.md).

## Run it

Start the backend first (see [ARCHITECTURE.md](ARCHITECTURE.md#running-it)), then:

```bash
npm install
npx expo start
```

Press `i` for the iOS simulator, or `a` for an Android emulator. Android needs Android Studio with an emulator set up. You can also scan the QR code with Expo Go on a phone.

## Checks

```bash
npx tsc --noEmit
npx expo lint
backend/.venv/bin/python backend/manage.py export_openapi && npm run api:types   # after changing the API
(cd backend && .venv/bin/python -m pytest)
```

## Tricity public-records fetcher

`tools/tricity-fetcher` collects Haryana RERA and other Tricity public records on a Mac in India. It is standard-library Python, separate from the app and backend. See its [README](tools/tricity-fetcher/README.md). Its installer refuses to run from Desktop, Documents or Downloads, so copy that folder to `~/tricity-fetcher` before installing the hourly job.

```bash
(cd tools/tricity-fetcher && python3 -m unittest discover -s tests)
```

## Next

- Connect the real services in the backend: phone OTP, DigiLocker, Razorpay or Cashfree UPI AutoPay and escrow, Leegality or Digio eSign, and the Qube meter API. Each runs as a local fake today.
- Passkey sign-in (WebAuthn), which needs a development build.
- Store builds: `npx eas-cli@latest build -p ios` and `-p android`.
