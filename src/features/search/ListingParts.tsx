import type { ReactNode } from 'react';
import { View } from 'react-native';
import { router } from 'expo-router';
import { Badge, Btn, Card, Chip, Dot, List, Note, Row, Stars, T, C, GENDER_COLOR, SP, dayHour, useWide } from '@/design';
import { inr, type Schemas } from '@/core/api';

type Listing = Schemas['ListingOut'];
type Application = Schemas['ApplicationOut'];
/* The sign-up gate: browsing is open, acting needs a verified account; sign-up then carries on to `next`. */
export type Go = (why: string, next: string) => void;

const closes = (iso?: string | null) => (iso ? dayHour(iso) : 'Friday 6 pm');
const titleCase = (s: string) => s.toLowerCase().replace(/(^|\s)\S/g, c => c.toUpperCase());
const moveIn = (iso: string) => new Date(iso).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' });

/* A section heading of the wide page. */
const Heading = ({ children }: { children: string }) => <View accessibilityRole="header" style={{ paddingTop: SP.sm }}><T v="h3">{children}</T></View>;

/* Name, gender, area, rating. On a wide website the name is the big title and the address follows. */
export function ListingTitle({ p }: { p: Listing }) {
  const wide = useWide();
  const meta = (
    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
      <Dot color={GENDER_COLOR[p.gender]} /><T v="sm">{p.gender} · {p.area}</T>
      {p.rating != null && <><Stars value={p.rating} /><T v="sm">{p.rating.toFixed(1)} ({p.stays} {p.stays === 1 ? 'stay' : 'stays'})</T></>}
    </View>
  );
  return (
    <>
      <View style={{ flexDirection: 'row', justifyContent: wide ? 'flex-start' : 'space-between', alignItems: 'center', gap: wide ? 14 : 8, flexWrap: wide ? 'wrap' : 'nowrap' }}>
        <T v={wide ? 'display' : 'h2'} style={wide ? undefined : { flex: 1 }}>{p.name}</T>
        {p.verified_owner && <Badge label="Verified owner" tone="ok" />}
      </View>
      {meta}
      {wide && <T v="sm">{p.address}</T>}
    </>
  );
}

/* The rooms that have a free bed, with the action for each. */
export function ListingRooms({ p, live, go }: { p: Listing; live: Application | undefined; go: Go }) {
  const wide = useWide();
  return (
    <>
      {wide ? <Heading>Rooms with a free bed</Heading> : <T v="label">Rooms with a free bed</T>}
      {p.rooms.length === 0 ? <Note tone="soft">Every bed is taken for now. Schedule a tour to be first when one frees up.</Note> : (
        <List>
          {p.rooms.map((r, i) => (
            <Row key={r.number} last={i === p.rooms.length - 1}
              left={<View style={{ gap: 2 }}>
                <T v="bodyBold">Room {r.number} · {r.kind_label}</T>
                <T v="sm">{inr(r.rent_paise)} a bed · {r.free} of {r.beds} free</T>
                {r.instant && r.free > 0 && <T v="sm" style={{ color: C.ok }}>Instant booking: book now, no waiting for the owner</T>}
                {r.bidding && <T v="sm" style={{ color: C.warn }}>Up for bids until {closes(r.closes_at)}{r.bids ? ` · ${r.bids} bid${r.bids > 1 ? 's' : ''}` : ''}</T>}
              </View>}
              right={!live ? <Chip label={r.bidding ? 'Bid' : r.instant ? 'Book now' : 'Request'} onPress={() => go(r.bidding ? 'offer' : 'book', `/apply/${p.id}?room=${r.number}`)} /> : undefined} />
          ))}
        </List>
      )}
    </>
  );
}

/* What the stay costs. */
export function ListingFacts({ p }: { p: Listing }) {
  const wide = useWide();
  return (
    <>
      {wide && <Heading>What you pay</Heading>}
      <List>
        <Row left="Deposit" right={`${p.deposit_months} month, in escrow`} />
        <Row left="Electricity" right={`By meter, ₹${(p.tariff_paise / 100).toFixed(2)}/unit`} />
        <Row left="Meals" right={p.meals} />
        <Row left="Payment" right="In the app only" />
        <Row left="Fees" right="None, Pakka Ghar is free" last />
      </List>
    </>
  );
}

/* The two big buttons: the request (or the live request) and the tour. */
export function ListingActions({ p, live, go }: { p: Listing; live: Application | undefined; go: Go }) {
  /* being checked by the trust team, or paused: a request already made carries on, but nothing new starts here */
  if (!p.taking_tenants && !live) return <Note tone="soft">Not taking new tenants right now. The PG is being checked by our trust team or paused by its owner.</Note>;
  return (
    <>
      {live
        ? <Btn label={live.status === 'accepted' ? 'Accepted: sign and pay' : 'See your request'} onPress={() => router.push(live.status === 'accepted' ? `/book/${p.id}` : '/stay')} />
        : p.rooms.length > 0 && <Btn label="Request a bed" onPress={() => go('book', `/apply/${p.id}`)} />}
      <Btn kind="secondary" label="Schedule a tour" onPress={() => go('visit', `/tour/${p.id}`)} />
    </>
  );
}

export function ListingExplainer() {
  return <T v="sm">Request a bed alone or with roommates. The owner sees your verified record and accepts; then you sign and pay the deposit in one go. Pakka Ghar is free: no brokerage, no fees.</T>;
}

/* The map section of a wide page: heading, map, address. The map itself is passed in so the page builds it once. */
export function ListingWhere({ p, map }: { p: Listing; map: ReactNode }) {
  return (
    <>
      <Heading>Where it is</Heading>
      {map}
      <T v="sm">{p.address}</T>
      <T v="sm">{titleCase(p.city)}</T>
    </>
  );
}

const FactLine = ({ k, v }: { k: string; v: string }) => (
  <View style={{ flexDirection: 'row', justifyContent: 'space-between', gap: 12 }}><T v="sm">{k}</T><T v="smBold">{v}</T></View>
);

/* The booking panel on a wide website. */
export function ListingBookingPanel({ p, live, go }: { p: Listing; live: Application | undefined; go: Go }) {
  const free = p.rooms.filter(r => r.free > 0);
  const from = free.length > 0 ? Math.min(...free.map(r => r.rent_paise)) : p.rent_paise;
  return (
    <Card style={{ padding: 20, gap: 14 }}>
      <View style={{ gap: 2 }}>
        <T v="label">From</T>
        <View style={{ flexDirection: 'row', alignItems: 'baseline', gap: 6, flexWrap: 'wrap' }}>
          <T v="h1" style={{ fontSize: 34, lineHeight: 40 }}>{inr(from)}</T>
          <T v="sm">/bed a month</T>
        </View>
      </View>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
        {p.free === 0 ? <Badge label="Full for now" /> : p.hot ? <Badge label="High demand" tone="warn" /> : <Badge label={p.free === 1 ? '1 bed free' : `${p.free} beds free`} tone="ok" />}
        <T v="sm">Move in from {moveIn(p.move_in_on)}</T>
      </View>
      <View style={{ gap: 8 }}><ListingActions p={p} live={live} go={go} /></View>
      <View style={{ gap: 6, borderTopWidth: 1, borderTopColor: C.line, paddingTop: 12 }}>
        <FactLine k="Deposit" v={`${p.deposit_months} month, in escrow`} />
        <FactLine k="Fees" v="None" />
        <FactLine k="Payment" v="In the app only" />
      </View>
    </Card>
  );
}
