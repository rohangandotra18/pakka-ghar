import { useEffect, useRef, useState } from 'react';
import { api, ok, type Schemas } from '@/core/api';

export const MIN_CHARS = 2;
const WAIT_MS = 250;

type Answer = { q: string; places: Schemas['PlaceOut'][]; pgs: Schemas['ListingOut'][]; failed: boolean };

/* Places and PGs matching what is typed. Unlike useQuery it does not reload on focus or on a global refresh, and it never
   lets an old answer win: every run takes a number from `seq`, and leaving the effect (new text, or unmount) moves
   `seq` on, so a slow answer for "sec" finds its number out of date and is dropped instead of replacing "sector 22". */
export function useTypeahead(text: string) {
  const q = text.trim();
  const [answer, setAnswer] = useState<Answer | null>(null);
  const seq = useRef(0);
  useEffect(() => {
    const mine = ++seq.current;
    if (q.length < MIN_CHARS) return;
    const timer = setTimeout(async () => {
      let next: Answer;
      try {
        const [places, pgs] = await Promise.all([
          ok(api.GET('/api/places', { params: { query: { q, limit: 6 } } })),
          ok(api.GET('/api/listings', { params: { query: { q, limit: 4 } } })),
        ]);
        next = { q, places, pgs, failed: false };
      } catch {
        next = { q, places: [], pgs: [], failed: true };
      }
      if (mine === seq.current) setAnswer(next);
    }, WAIT_MS);
    return () => { clearTimeout(timer); seq.current = mine + 1; };
  }, [q]);
  /* only an answer to the text as it is now counts; until then the panel says "Searching…" */
  return answer && answer.q === q ? answer : null;
}
