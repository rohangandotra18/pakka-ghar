import { useState } from 'react';
import { Back, Btn, Card, Chip, Chips, Loading, Note, Screen, T } from '@/design';
import { api, ok, useAction, useQuery } from '@/core/api';

/* When tenants can book a tour of the PG. Tours are offered in these hours, one tenant per slot, from two hours
   ahead; the owner confirms each request from Today. */
const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
const STARTS = ['08:00', '09:00', '10:00', '11:00', '12:00', '14:00', '16:00'];
const ENDS = ['12:00', '14:00', '16:00', '17:00', '18:00', '19:00', '20:00', '21:00'];
const LENGTHS = [15, 30, 45, 60];
const clock = (hhmm: string) => {
  const [h, m] = hhmm.split(':').map(Number);
  return `${h % 12 || 12}${m ? `:${String(m).padStart(2, '0')}` : ''} ${h < 12 ? 'am' : 'pm'}`;
};

type Hours = { days: number[]; start: string; end: string; minutes: number };

export default function TourHoursScreen() {
  const { act } = useAction();
  const current = useQuery(() => ok(api.GET('/api/owner/tour-hours')));   // works while the PG is still a draft too
  /* the saved hours until the owner changes something, then their edit */
  const [edited, setEdited] = useState<Hours | null>(null);
  const h = edited ?? current.data ?? null;

  if (!h) return <Screen><Back /><Loading error={current.error} retry={current.reload} /></Screen>;
  const set = (x: Partial<Hours>) => setEdited({ ...h, ...x });
  const toggleDay = (d: number) => set({ days: h.days.includes(d) ? h.days.filter(x => x !== d) : [...h.days, d].sort() });
  const valid = h.days.length > 0 && h.start < h.end;
  const save = () => act(() => ok(api.PUT('/api/owner/tour-hours', { body: h })), 'Tour hours saved. Tenants see the new times straight away.');

  return (
    <Screen>
      <Back />
      <T v="h2">Tour hours</T>
      <T v="sm">When tenants can ask to see the PG. Each slot takes one tenant, and you confirm every request from Today.</T>
      <Card>
        <T v="label">Days</T>
        <Chips>{DAYS.map((d, i) => <Chip key={d} label={d} on={h.days.includes(i)} onPress={() => toggleDay(i)} />)}</Chips>
        <T v="label">From</T>
        <Chips>{STARTS.map(t => <Chip key={t} label={clock(t)} on={h.start === t} onPress={() => set({ start: t })} />)}</Chips>
        <T v="label">Until</T>
        <Chips>{ENDS.map(t => <Chip key={t} label={clock(t)} on={h.end === t} onPress={() => set({ end: t })} />)}</Chips>
        <T v="label">Each tour</T>
        <Chips>{LENGTHS.map(m => <Chip key={m} label={`${m} min`} on={h.minutes === m} onPress={() => set({ minutes: m })} />)}</Chips>
      </Card>
      {!h.days.length && <Note>Pick at least one day, or tenants can’t book a tour.</Note>}
      {h.days.length > 0 && h.start >= h.end && <Note>The end time has to be after the start.</Note>}
      {valid && <T v="sm">{h.days.map(d => DAYS[d]).join(', ')} · {clock(h.start)} to {clock(h.end)} · {h.minutes}-minute tours</T>}
      <Btn label="Save tour hours" disabled={!valid} onPress={save} />
    </Screen>
  );
}
