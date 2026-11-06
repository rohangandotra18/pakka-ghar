import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { Platform } from 'react-native';
import * as SecureStore from './storage';
import { api, ok, onUnauthorized, setToken, type Schemas } from '../api/client';

/* The app's own state: who is signed in (one account), toasts, and a version number that tells every screen to
   reload after a change. Everything else lives on the server.

   One app, one sign-in. What you see follows the account: someone who runs a PG sees the owner side, everyone
   else the tenant side. Only the website lets an owner switch to the tenant side and back (`setRole`). */
export type Role = 'tenant' | 'owner';
type Me = Schemas['MeOut'];
type Session = { token: string; me: Me };
type State = {
  /* the side on screen, worked out from the account (and, on the website, the owner's own choice) */
  role: Role | null;
  session: Session | null;
  /* the same session under the side's name, for screens written for one side */
  tenant: Session | null;
  owner: Session | null;
  booted: boolean;
};

type Ctx = {
  s: State;
  /* website only: an owner switching between their dashboard and the tenant side */
  setRole: (r: Role) => void;
  canSwitch: boolean;
  signIn: (role: Role | null, token: string, me: Me) => Promise<void>;
  updateMe: (role: Role | null, me: Me) => void;
  signOut: (role?: Role) => Promise<void>;
  /* bump after any change so screens refetch */
  refresh: () => void;
  version: number;
  toast: (m: string) => void;
  toastMsg: string;
  /* verified and can act as a tenant; runs a PG */
  tenantReady: boolean;
  ownerReady: boolean;
};
const StoreCtx = createContext<Ctx | null>(null);
const KEY = { session: 'pg.session', view: 'pg.view', oldTenant: 'pg.session.tenant', oldOwner: 'pg.session.owner', oldRole: 'pg.role' } as const;
const WEB = Platform.OS === 'web';

const isOwner = (sess: Session | null) => !!sess?.me.memberships.length;
const sideFor = (sess: Session | null, view: Role | null): Role | null =>
  !sess ? null : isOwner(sess) ? (WEB && view === 'tenant' ? 'tenant' : 'owner') : 'tenant';

export function StoreProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  const [view, setView] = useState<Role | null>(null);   // website: the owner's chosen side
  const [booted, setBooted] = useState(false);
  const [version, setVersion] = useState(0);
  const [toastMsg, setToast] = useState('');
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  /* restore the saved sign-in (moving over the older one-per-side sign-ins), and drop it if the server no
     longer accepts it */
  useEffect(() => {
    (async () => {
      const load = async (k: string): Promise<Session | null> => {
        try { const raw = await SecureStore.getItem(k); return raw ? JSON.parse(raw) : null; } catch { return null; }
      };
      let saved = await load(KEY.session);
      if (!saved) {
        const [t, o] = await Promise.all([load(KEY.oldTenant), load(KEY.oldOwner)]);
        saved = o ?? t;
        await Promise.all([KEY.oldTenant, KEY.oldOwner, KEY.oldRole].map(k => SecureStore.deleteItem(k).catch(() => {})));
        if (saved) await SecureStore.setItem(KEY.session, JSON.stringify(saved)).catch(() => {});
      }
      let checked: Session | null = saved;
      if (saved) {
        try {
          checked = { ...saved, me: await ok(api.GET('/api/me', { headers: { Authorization: `Bearer ${saved.token}` } })) };
        } catch (e) {
          if ((e as { status?: number }).status === 401) { await SecureStore.deleteItem(KEY.session).catch(() => {}); checked = null; }
          /* offline: keep it */
        }
      }
      let v: Role | null = null;
      try { v = (await SecureStore.getItem(KEY.view)) as Role | null; } catch { /* first launch */ }
      setSession(checked);
      setView(v);
      setBooted(true);
    })();
  }, []);

  /* a token the server stops accepting mid-use is dropped, so the person is asked to sign in again */
  useEffect(() => {
    onUnauthorized(token => {
      setSession(p => {
        if (!p || p.token !== token) return p;
        SecureStore.deleteItem(KEY.session).catch(() => {});
        return null;
      });
    });
    return () => onUnauthorized(null);
  }, []);

  useEffect(() => { setToken(session?.token ?? null); }, [session]);

  const setRole = useCallback((role: Role) => {
    if (!WEB) return;          // the phone app follows the account
    setView(role);
    SecureStore.setItem(KEY.view, role).catch(() => {});
  }, []);
  const signIn = useCallback(async (_role: Role | null, token: string, me: Me) => {
    const sess = { token, me };
    setToken(token);
    setSession(sess);
    await SecureStore.setItem(KEY.session, JSON.stringify(sess)).catch(() => {});
  }, []);
  const updateMe = useCallback((_role: Role | null, me: Me) => {
    setSession(p => {
      if (!p) return p;
      const next = { ...p, me };
      SecureStore.setItem(KEY.session, JSON.stringify(next)).catch(() => {});
      return next;
    });
  }, []);
  const signOut = useCallback(async () => {
    if (session) await api.POST('/api/auth/logout', { headers: { Authorization: `Bearer ${session.token}` } }).catch(() => {});
    setSession(null);
    await SecureStore.deleteItem(KEY.session).catch(() => {});
  }, [session]);
  const refresh = useCallback(() => setVersion(v => v + 1), []);
  const toast = useCallback((m: string) => {
    setToast(m);
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => setToast(''), 2800);
  }, []);

  const role = sideFor(session, view);
  const s: State = useMemo(() => ({ role, session, tenant: session, owner: session, booted }), [role, session, booted]);
  const tenantReady = !!session?.me.verified;
  const ownerReady = isOwner(session);
  const canSwitch = WEB && ownerReady;
  const value = useMemo(() => ({ s, setRole, canSwitch, signIn, updateMe, signOut, refresh, version, toast, toastMsg, tenantReady, ownerReady }),
    [s, setRole, canSwitch, signIn, updateMe, signOut, refresh, version, toast, toastMsg, tenantReady, ownerReady]);
  return <StoreCtx.Provider value={value}>{children}</StoreCtx.Provider>;
}
export function useStore() {
  const c = useContext(StoreCtx);
  if (!c) throw new Error('useStore outside StoreProvider');
  return c;
}
