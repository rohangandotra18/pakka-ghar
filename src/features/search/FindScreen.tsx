import { useWide } from '@/design';
import { FindNarrow } from './FindNarrow';
import { FindWide } from './FindWide';
import { useFind } from './useFind';

/* Find: the state lives in useFind; a wide website lays it out as a list beside a full-height map, everything else as
   one column. */
export default function Find() {
  const f = useFind();
  return useWide() ? <FindWide f={f} /> : <FindNarrow f={f} />;
}
