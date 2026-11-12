import { Pressable, View } from 'react-native';
import { router, usePathname, type Href } from 'expo-router';
import { Btn, C, T, Wordmark } from '@/design';
import { AccountMenu } from '@/shared';
import { useStore } from '@/core/session';

/* The website's header on a wide screen: 64 px, logo and the main links at the left, sign-in or the account menu at
   the right. RootLayout draws it once above the navigation stack, so it shows on every page except the owner
   dashboard (which has its own sidebar). Which links show follows who is signed in:
     nobody          Find a PG
     tenant side     Find, My stay, Requests, History
     owner side      Dashboard (owner pages outside the dashboard, such as a resident)
   `match` lists the paths that light a link, so a PG's page lights "Find". */
type Link = { label: string; to: Href; match: string[] };
const NOBODY: Link[] = [{ label: 'Find a PG', to: '/find', match: ['/find', '/pg'] }];
const TENANT: Link[] = [
  { label: 'Find', to: '/find', match: ['/find', '/pg'] },
  { label: 'My stay', to: '/stay', match: ['/stay'] },
  { label: 'Requests', to: '/requests', match: ['/requests'] },
  { label: 'History', to: '/history', match: ['/history'] },
];
const OWNER: Link[] = [{ label: 'Dashboard', to: '/today', match: ['/today'] }];

const SIGN_IN = { pathname: '/onboarding/tenant', params: { why: 'signin' } } as const;

type PressState = { hovered?: boolean; focused?: boolean };

export function SiteHeader() {
  const { s } = useStore();
  const path = usePathname();
  const me = s.session?.me;
  const links = !me ? NOBODY : s.role === 'owner' ? OWNER : TENANT;
  const home: Href = !me ? '/' : s.role === 'owner' ? '/today' : '/find';
  const lit = (l: Link) => l.match.some(m => path === m || path.startsWith(m + '/'));
  return (
    <View style={{ height: 64, flexDirection: 'row', alignItems: 'center', paddingHorizontal: 24, backgroundColor: C.surface, borderBottomWidth: 1, borderBottomColor: C.line, zIndex: 20 }}>
      <Pressable onPress={() => router.navigate(home)} accessibilityRole="link" accessibilityLabel="Pakka Ghar home" style={{ marginRight: 32 }}>
        <Wordmark size={30} />
      </Pressable>
      <View style={{ flexDirection: 'row', alignSelf: 'stretch', gap: 8 }}>
        {links.map(l => {
          const on = lit(l);
          /* the 2 px underline sits on the bar's bottom border (marginBottom -1 covers the hairline) */
          return (
            <Pressable key={l.label} onPress={() => router.navigate(l.to)} accessibilityRole="link" accessibilityState={{ selected: on }}
              style={({ hovered }: PressState) => ({ justifyContent: 'center', paddingHorizontal: 12, paddingTop: 3, marginBottom: -1, borderBottomWidth: 2, borderBottomColor: on ? C.accent : 'transparent', backgroundColor: hovered && !on ? C.bg : 'transparent' })}>
              <T v="bodyBold" style={{ color: on ? C.accent : C.ink }}>{l.label}</T>
            </Pressable>
          );
        })}
      </View>
      <View style={{ flex: 1 }} />
      {me ? <AccountMenu floating /> : (
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 16 }}>
          <Pressable onPress={() => router.push('/onboarding/owner')} accessibilityRole="link"
            style={({ hovered }: PressState) => ({ paddingVertical: 6, opacity: hovered ? 0.7 : 1 })}>
            <T v="bodyBold" style={{ color: C.accent }}>List your PG</T>
          </Pressable>
          <Btn small kind="secondary" label="Sign in" onPress={() => router.push(SIGN_IN)} />
        </View>
      )}
    </View>
  );
}
