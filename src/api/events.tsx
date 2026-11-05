import { useEffect } from 'react';
import { useStore } from '@/lib/store';
import { API_BASE } from './client';

/* Live updates: the server streams one event per notification (an offer arrives, rent is paid, a repair is
   assigned). React Native's fetch can't stream, but XMLHttpRequest reports progress, so read the stream with it.
   Each event shows as a toast and makes every screen reload. */
export function LiveEvents() {
  const { s, refresh, toast } = useStore();
  const token = s.role === 'owner' ? s.owner?.token : s.tenant?.token;
  useEffect(() => {
    if (!token) return;
    let xhr: XMLHttpRequest | null = null;
    let stopped = false;
    let last = 0;
    let retry: ReturnType<typeof setTimeout> | undefined;
    const connect = () => {
      const x = new XMLHttpRequest();
      xhr = x;
      let seen = 0;
      x.open('GET', `${API_BASE}/api/events${last ? `?after=${last}` : ''}`);
      x.setRequestHeader('Authorization', `Bearer ${token}`);
      x.setRequestHeader('Accept', 'text/event-stream');
      x.onprogress = () => {
        const fresh = x.responseText.slice(seen);
        const end = fresh.lastIndexOf('\n\n');
        if (end < 0) return;
        seen += end + 2;
        let changed = false;
        for (const block of fresh.slice(0, end).split('\n\n')) {
          const data = block.split('\n').filter(l => l.startsWith('data: ')).map(l => l.slice(6)).join('\n');
          if (!data) continue;
          try {
            const n = JSON.parse(data) as { id: number; title: string };
            last = Math.max(last, n.id);
            toast(n.title);
            changed = true;
          } catch { /* a malformed event is skipped */ }
        }
        if (changed) refresh();
      };
      x.onloadend = () => { if (!stopped) retry = setTimeout(connect, 3000); };
      x.send();
    };
    connect();
    return () => { stopped = true; if (retry) clearTimeout(retry); xhr?.abort(); };
  }, [token, refresh, toast]);
  return null;
}
