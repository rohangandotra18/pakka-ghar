import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import * as SecureStore from './storage';
import { api, ok, setToken, type Schemas } from '@/api/client';

/* The app's own state: which side is on screen, the signed-in person for each side, toasts, and a version
   number that tells every screen to reload after a change. Everything else lives on the server. */
export type Role = 'tenant' | 'owner';
type Me = Schemas['MeOut'];
type Session = { token: string; me: Me };
type State = { role: Role | null; tenant: Session | null; owner: Session | null; booted: boolean };

type Ctx = {
  s: State;
  setRole: (r: Role) => void;
  signIn: (role: Role, token: string, me: Me) => Promise<void>;
  updateMe: (role: Role, me: Me) => void;
  signOut: (role: Role) => Promise<void>;
  /* bump after any change so screens refetch */
  refresh: () => void;
  version: number;
  toast: (m: string) => void;
  toastMsg: string;
  /* tenant side is verified and can act; owner side has a property */
  tenantReady: boolean;
  ownerReady: boolean;
};
const StoreCtx = createContext<Ctx | null>(null);
const KEY = { tenant: 'pg.session.tenant', owner: 'pg.session.owner', role: 'pg.role' } as const;

export function StoreProvider({ children }: { children: ReactNode }) {
  const [s, setS] = useState<State>({ role: null, tenant: null, owner: null, booted: false });
  const [version, setVersion] = useState(0);
  const [toastMsg, setToast] = useState('');
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  /* restore saved sessions, and drop any the server no longer accepts */
  useEffect(() => {
    (async () => {
      const load = async (k: string): Promise<Session | null> => {
        try { const raw = await SecureStore.getItem(k); return raw ? JSON.parse(raw) : null; } catch { return null; }
      };
      const [tenant, owner] = await Promise.all([load(KEY.tenant), load(KEY.owner)]);
      let role: Role | null = null;
      try { role = (await SecureStore.getItem(KEY.role)) as Role | null; } catch { /* first launch */ }
      const check = async (sess: Session | null, k: string) => {
        if (!sess) return null;
        try {
          const me = await ok(api.GET('/api/me', { headers: { Authorization: `Bearer ${sess.token}` } }));
          return { ...sess, me };
        } catch (e) {
          if ((e as { status?: number }).status === 401) { await SecureStore.deleteItem(k).catch(() => {}); return null; }
          return sess; /* offline: keep it */
        }
      };
      const [t, o] = await Promise.all([check(tenant, KEY.tenant), check(owner, KEY.owner)]);
      setS({ role, tenant: t, owner: o, booted: true });
    })();
  }, []);

  useEffect(() => { setToken(s.role === 'owner' ? s.owner?.token ?? null : s.tenant?.token ?? null); }, [s.role, s.tenant, s.owner]);

  const setRole = useCallback((role: Role) => {
    setS(p => ({ ...p, role }));
    SecureStore.setItem(KEY.role, role).catch(() => {});
  }, []);
  const signIn = useCallback(async (role: Role, token: string, me: Me) => {
    const sess = { token, me };
    setToken(token);
    setS(p => ({ ...p, role, [role]: sess }));
    await Promise.all([SecureStore.setItem(KEY[role], JSON.stringify(sess)), SecureStore.setItem(KEY.role, role)]).catch(() => {});
  }, []);
  const updateMe = useCallback((role: Role, me: Me) => {
    setS(p => {
      const cur = p[role];
      if (!cur) return p;
      const next = { ...cur, me };
      SecureStore.setItem(KEY[role], JSON.stringify(next)).catch(() => {});
      return { ...p, [role]: next };
    });
  }, []);
  const signOut = useCallback(async (role: Role) => {
    const sess = s[role];
    if (sess) await api.POST('/api/auth/logout', { headers: { Authorization: `Bearer ${sess.token}` } }).catch(() => {});
    setS(p => ({ ...p, [role]: null }));
    await SecureStore.deleteItem(KEY[role]).catch(() => {});
  }, [s]);
  const refresh = useCallback(() => setVersion(v => v + 1), []);
  const toast = useCallback((m: string) => {
    setToast(m);
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => setToast(''), 2800);
  }, []);
  const tenantReady = !!s.tenant?.me.verified;
  const ownerReady = !!s.owner?.me.memberships.length;
  const value = useMemo(() => ({ s, setRole, signIn, updateMe, signOut, refresh, version, toast, toastMsg, tenantReady, ownerReady }),
    [s, setRole, signIn, updateMe, signOut, refresh, version, toast, toastMsg, tenantReady, ownerReady]);
  return <StoreCtx.Provider value={value}>{children}</StoreCtx.Provider>;
}
export function useStore() {
  const c = useContext(StoreCtx);
  if (!c) throw new Error('useStore outside StoreProvider');
  return c;
}
