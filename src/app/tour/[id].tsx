import { useState } from 'react';
import { router, useLocalSearchParams } from 'expo-router';
import { Loading } from '@/components/Loading';
import { Back, Btn, Card, Chip, Chips, Field, Note, Screen, T } from '@/components/ui';
import { api, ok } from '@/api/client';
import { useAction, useQuery } from '@/api/hooks';

const dayKey = (iso: string) => new Date(iso).toLocaleDateString('en-CA', { timeZone: 'Asia/Kolkata' });
const dayLabel = (iso: string) => new Date(iso).toLocaleDateString('en-IN', { weekday: 'short', day: 'numeric', month: 'short', timeZone: 'Asia/Kolkata' });
const timeLabel = (iso: string) => new Date(iso).toLocaleTimeString('en-IN', { hour: 'numeric', minute: '2-digit', hour12: true, timeZone: 'Asia/Kolkata' }).toLowerCase();

/* Schedule a tour: pick a day and one of the owner's free times. The owner confirms in their app. */
export default function Tour() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const { act, busy } = useAction();
  const listing = useQuery(() => ok(api.GET('/api/listings/{slug}', { params: { path: { slug: id } } })), [id]);
  const q = useQuery(() => ok(api.GET('/api/listings/{slug}/tour-slots', { params: { path: { slug: id } } })), [id]);
  const mine = useQuery(() => ok(api.GET('/api/visits/mine')), [id]);
  const [day, setDay] = useState<string | null>(null);
  const [slot, setSlot] = useState<string | null>(null);
  const [note, setNote] = useState('');
  if (!q.data || !listing.data || !mine.data) return <Screen><Back /><Loading error={q.error ?? listing.error} retry={q.reload} /></Screen>;
  const upcoming = mine.data.find(v => v.listing === id && ['requested', 'confirmed'].includes(v.status) && new Date(v.slot) > new Date());
  const days = [...new Set(q.data.slots.map(dayKey))];
  const d = day ?? days[0];
  const times = q.data.slots.filter(s => dayKey(s) === d);
  if (upcoming) return (
    <Screen>
      <Back />
      <T v="h2">Your tour</T>
      <Card>
        <T v="bodyBold">{listing.data.name}</T>
        <T>{dayLabel(upcoming.slot)} at {timeLabel(upcoming.slot)}</T>
        <T v="sm">{upcoming.status === 'confirmed' ? 'Confirmed by the owner.' : 'Waiting for the owner to confirm.'}{upcoming.note ? ` · “${upcoming.note}”` : ''}</T>
      </Card>
      <Btn kind="secondary" label="Cancel this tour" disabled={busy} onPress={() => act(() => ok(api.POST('/api/visits/{visit_id}/cancel', { params: { path: { visit_id: upcoming.id } } })), 'Tour cancelled. Pick another time any time.')} />
    </Screen>
  );
  return (
    <Screen>
      <Back />
      <T v="h2">Schedule a tour</T>
      <T v="sm">{listing.data.name} · {listing.data.address}</T>
      {days.length === 0 ? <Note tone="soft">No tour times are free this week. Check back soon.</Note> : <>
        <T v="label">Day</T>
        <Chips>{days.map(k => <Chip key={k} label={dayLabel(q.data!.slots.find(s => dayKey(s) === k)!)} on={d === k} onPress={() => { setDay(k); setSlot(null); }} />)}</Chips>
        <T v="label">Time</T>
        <Chips>{times.map(s => <Chip key={s} label={timeLabel(s)} on={slot === s} onPress={() => setSlot(s)} />)}</Chips>
        <Field label="Anything for the owner?" value={note} onChangeText={setNote} placeholder="Optional, e.g. coming with a parent" />
        <Btn label={slot ? `Book tour, ${dayLabel(slot)} at ${timeLabel(slot)}` : 'Pick a time'} disabled={!slot || busy}
          onPress={() => act(async () => { await ok(api.POST('/api/visits', { body: { listing: id, slot, note } })); router.back(); }, 'Tour requested. The owner confirms in the app.')} />
      </>}
      <T v="sm">Tours are free. Never pay anything to see a PG.</T>
    </Screen>
  );
}
