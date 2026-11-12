import { Platform } from 'react-native';
import { usePathname } from 'expo-router';
import Head from 'expo-router/head';

/* The browser tab's title, description, colour and language, on the website only. Expo Router's `<Head>` (from
   `expo-router/head`) updates the page's <head> as the route changes. Nothing is drawn on a phone. */
const SUFFIX = 'Pakka Ghar';
const TITLES: [prefix: string, title: string][] = [
  ['/find', 'Find a PG'],
  ['/pg', 'PG'],
  ['/stay', 'My stay'],
  ['/requests', 'Requests'],
  ['/history', 'History'],
  ['/today', 'Today'],
  ['/applications', 'Requests to stay'],
  ['/beds', 'Beds'],
  ['/money', 'Money'],
  ['/more', 'PG settings'],
  ['/residents', 'Residents'],
  ['/resident', 'Resident'],
  ['/tickets', 'Repairs'],
  ['/staff', 'Trust team'],
  ['/onboarding/tenant', 'Sign in'],
  ['/onboarding/owner', 'List your PG'],
  ['/apply', 'Request to stay'],
  ['/book', 'Book your bed'],
  ['/agreement', 'Agreement'],
  ['/tour', 'Visit'],
  ['/rate', 'Rate your stay'],
  ['/request-new', 'New repair request'],
];
const HOME = 'Verified PGs in Chandigarh, Mohali and Panchkula';
const DESCRIPTION = 'Verified PGs in Chandigarh, Mohali and Panchkula. Real rent per bed, photos taken on site, no brokerage and no cash.';

export function titleFor(path: string): string {
  if (path === '/') return `${HOME} · ${SUFFIX}`;
  const hit = TITLES.find(([p]) => path === p || path.startsWith(p + '/'));
  return hit ? `${hit[1]} · ${SUFFIX}` : SUFFIX;
}

export function DocumentHead() {
  const path = usePathname();
  if (Platform.OS !== 'web') return null;
  return (
    <Head>
      <html lang="en-IN" />
      <title>{titleFor(path)}</title>
      <meta name="description" content={DESCRIPTION} />
      <meta name="theme-color" content="#0E6B50" />
    </Head>
  );
}
