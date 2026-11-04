# Pakka Ghar app

One React Native (Expo SDK 58) codebase for iOS and Android. It looks the same on both platforms because:

- every control is drawn by the app (tab bar, buttons, toggle, offer stepper, star input); there are no native switches, sliders or ripples
- Manrope and Bricolage Grotesque are bundled
- there are no platform shadows, only borders
- the slide animation is the same on both

Screens cover tenant and owner onboarding, offers on scarce beds, booking with escrow deposit, Aadhaar eSign and e-stamp, rent and electricity, requests (including "asked to pay in cash"), resident records, rental history and ratings. Everything uses sample data from `src/lib/data.ts`.

## Run it

```bash
npm install
npx expo start
```

Press `i` for the iOS simulator, or `a` for an Android emulator. Android needs Android Studio with an emulator set up. You can also scan the QR code with Expo Go on a phone.

## Checks

```bash
npx tsc --noEmit
npx expo lint
```

## Next

- Replace the drawn map with MapLibre (`@maplibre/maplibre-react-native`), reusing the website's vector tiles. This needs a development build (`npx expo run:ios|android`), not Expo Go.
- Connect the real services: phone OTP, DigiLocker, Razorpay or Cashfree UPI AutoPay and escrow, Leegality or Digio eSign, and the Qube meter API.
- Store builds: `npx eas-cli@latest build -p ios` and `-p android`.
