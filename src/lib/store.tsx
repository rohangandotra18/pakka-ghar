import { createContext, useCallback, useContext, useMemo, useRef, useState, type ReactNode } from 'react';
import { OWNER_REQUESTS, PGS, type PG, type Req } from './data';

/* App state for the prototype, held in memory. The real app keeps this on the server. */
export type Role = 'tenant' | 'owner';
type State = {
  role: Role | null;
  tenantReady: boolean;
  ownerReady: boolean;
  offer: { pgId: string; amount: number; months: number; placed: boolean; accepted: boolean } | null;
  booking: { paid: boolean; signed: boolean; stamped: boolean };
  rentPaid: boolean;
  autopay: boolean;
  myRequests: Req[];
  rated: boolean;
  ownerRequests: Req[];
  offersOpen: boolean;
  acceptedOffer: string | null;
  paidByApp: Record<string, boolean>;
  police: Record<string, string>;
  metersPaired: Record<string, boolean>;
  /* where each owner pinned their building; the same point is shown to tenants */
  pins: Record<string, { lat: number; lng: number }>;
  /* the tenant's current stay; empty until they book (or load the sample stay) */
  stay: { pgId: string; rent: number; room: string; since: string } | null;
};
const initial: State = {
  role: null, tenantReady: false, ownerReady: false, offer: null,
  booking: { paid: false, signed: false, stamped: false }, rentPaid: false, autopay: false,
  myRequests: [],
  rated: false, ownerRequests: OWNER_REQUESTS, offersOpen: true, acceptedOffer: null, paidByApp: {}, police: {}, metersPaired: {}, pins: {}, stay: null,
};
type Ctx = { s: State; set: (u: Partial<State> | ((s: State) => Partial<State>)) => void; toast: (m: string) => void; toastMsg: string };
const StoreCtx = createContext<Ctx | null>(null);

export function StoreProvider({ children }: { children: ReactNode }) {
  const [s, setS] = useState<State>(initial);
  const [toastMsg, setToast] = useState('');
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const set = useCallback((u: Partial<State> | ((s: State) => Partial<State>)) => setS(prev => ({ ...prev, ...(typeof u === 'function' ? u(prev) : u) })), []);
  const toast = useCallback((m: string) => {
    setToast(m);
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => setToast(''), 2600);
  }, []);
  const value = useMemo(() => ({ s, set, toast, toastMsg }), [s, set, toast, toastMsg]);
  return <StoreCtx.Provider value={value}>{children}</StoreCtx.Provider>;
}
export function useStore() {
  const c = useContext(StoreCtx);
  if (!c) throw new Error('useStore outside StoreProvider');
  return c;
}
export const pgById = (id?: string) => PGS.find(p => p.id === id) ?? PGS[0];
/* the owner's own pin wins over the sample position */
export const pinOf = (p: PG, pins: State['pins']) => pins[p.id] ?? { lat: p.lat, lng: p.lng };
/* the demo owner (Jatinder) runs this PG */
export const OWNER_PG = 'sidhu';
/* a sample stay for the demo tenant, Simran, so the stay screens can be seen without booking */
export const SAMPLE_STAY = { pgId: 'gurnoor', rent: 10000, room: '204', since: 'Aug 2026' };
export const SAMPLE_REQUEST: Req = { id: 'R-118', who: 'You', room: '204', cat: 'Electrical', text: 'Ceiling fan makes a grinding noise', status: 'Assigned', at: 'Today', to: 'Gurmeet (electrician)' };
/* who gets assigned for each kind of request */
export const ASSIGNEE: Record<string, string> = { Electrical: 'Gurmeet (electrician)', Plumbing: 'Raju (plumber)', 'Wi-Fi': 'Airtel Xstream support', Cleaning: 'Housekeeping', Furniture: 'Ramesh (carpenter)' };
