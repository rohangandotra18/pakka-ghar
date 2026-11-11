import { View } from 'react-native';
import { Btn, Card, Chip, Chips, T, rupees } from '@/design';
import { countFilters, type Filters, type Gender, type RoomKind } from './findState';

const FOR: { value: Gender; label: string }[] = [{ value: 'Boys', label: 'Boys' }, { value: 'Girls', label: 'Girls' }, { value: 'Co-ed', label: 'Co-ed' }];
const RENT = [8000, 10000, 12000, 15000].map(value => ({ value, label: rupees(value) }));
const ROOM: { value: RoomKind; label: string }[] = [{ value: 'single', label: 'Single' }, { value: 'double', label: 'Double' }, { value: 'triple', label: 'Triple' }];

/* One row of single-choice chips: pressing the lit one clears it. */
function Group<V extends string | number>({ title, options, value, onChange }: { title: string; options: { value: V; label: string }[]; value: V | undefined; onChange: (v: V | undefined) => void }) {
  return (
    <View style={{ gap: 6 }}>
      <T v="label">{title}</T>
      <Chips>{options.map(o => <Chip key={o.value} label={o.label} on={value === o.value} onPress={() => onChange(value === o.value ? undefined : o.value)} />)}</Chips>
    </View>
  );
}

export function FilterPanel({ filters, onChange }: { filters: Filters; onChange: (f: Filters) => void }) {
  return (
    <Card>
      <Group title="For" options={FOR} value={filters.gender} onChange={gender => onChange({ ...filters, gender })} />
      <Group title="Rent up to" options={RENT} value={filters.rent} onChange={rent => onChange({ ...filters, rent })} />
      <Group title="Room" options={ROOM} value={filters.kind} onChange={kind => onChange({ ...filters, kind })} />
      {countFilters(filters) > 0 && <Btn kind="secondary" small label="Clear filters" onPress={() => onChange({})} />}
    </Card>
  );
}
