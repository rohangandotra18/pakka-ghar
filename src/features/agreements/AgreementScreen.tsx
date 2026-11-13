import { useState } from 'react';
import { router, useLocalSearchParams } from 'expo-router';
import { Image, View } from 'react-native';
import { Loading, Otp, Back, Badge, Btn, Card, Note, Screen, T, C, R } from '@/design';
import { API_BASE, api, ok, useAction, useQuery } from '@/core/api';

/* Read the agreement page by page, then sign it with a one-time code sent to your phone. The owner signs when
   accepting; the resident signs here before paying. After both have signed, the pages shown are the signed copy
   with its certificate page. */
export default function AgreementScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const { act, busy } = useAction();
  const q = useQuery(() => ok(api.GET('/api/agreements/{booking_id}', { params: { path: { booking_id: id } } })), [id]);
  const [seen, setSeen] = useState<Record<number, boolean>>({});
  const [failed, setFailed] = useState<Record<number, boolean>>({});
  const [challenge, setChallenge] = useState<{ id: string; code: string; last4: string } | null>(null);
  const d = q.data;
  if (!d) return <Screen><Back /><Loading error={q.error} retry={q.reload} /></Screen>;
  const mine = d.signatures.find(x => x.role === d.my_role);
  const theirs = d.signatures.find(x => x.role !== d.my_role);
  const total = d.signed ? d.signed_pages : d.pages;
  const read = Object.keys(seen).length;
  const canSign = !mine;
  const markSeen = (n: number) => () => { setSeen(x => (x[n] ? x : { ...x, [n]: true })); setFailed(x => (x[n] ? { ...x, [n]: false } : x)); };
  /* page links expire after 15 minutes; a page that won't load gets fresh links rather than blocking signing for good */
  const reloadPages = () => { setFailed({}); q.reload(); };
  const broken = Object.keys(failed).filter(k => failed[+k]).length;
  return (
    <Screen>
      <Back />
      <T v="h2">{d.signed ? 'Signed agreement' : 'Your agreement'}</T>
      <T v="sm">{d.source === 'owner' ? 'The owner’s own agreement, with a cover page from Pakka Ghar' : 'The standard Pakka Ghar agreement'} · {total} page{total > 1 ? 's' : ''}</T>
      <View style={{ flexDirection: 'row', gap: 6, flexWrap: 'wrap' }}>
        <Badge label={d.signatures.some(x => x.role === 'tenant') ? 'Resident signed' : 'Resident to sign'} tone={d.signatures.some(x => x.role === 'tenant') ? 'ok' : 'warn'} />
        <Badge label={d.signatures.some(x => x.role === 'owner') ? 'Owner signed' : 'Owner to sign'} tone={d.signatures.some(x => x.role === 'owner') ? 'ok' : 'warn'} />
      </View>
      {Array.from({ length: total }, (_, i) => i + 1).map(n => (
        <View key={`${n}-${d.signed}`} style={{ gap: 4 }}>
          {/* each page comes as a signed link that only works for this agreement and expires in 15 minutes */}
          {failed[n] ? (
            <View style={{ width: '100%', aspectRatio: 0.707, borderRadius: R.sm, borderWidth: 1, borderColor: C.line, backgroundColor: C.surface2, alignItems: 'center', justifyContent: 'center', gap: 10, padding: 20 }}>
              <T v="bodyBold" style={{ textAlign: 'center' }}>Page {n} didn’t load</T>
              <T v="sm" style={{ textAlign: 'center' }}>The link may have run out, or the connection dropped.</T>
              <Btn small kind="secondary" label="Load the pages again" onPress={reloadPages} />
            </View>
          ) : (
            <Image source={{ uri: `${API_BASE}${d.page_urls[n - 1]}` }} onLoad={markSeen(n)} onError={() => setFailed(x => ({ ...x, [n]: true }))} resizeMode="contain" accessibilityLabel={`Page ${n} of ${total}`}
              style={{ width: '100%', aspectRatio: 0.707, borderRadius: R.sm, borderWidth: 1, borderColor: C.line, backgroundColor: C.surface }} />
          )}
          <T v="sm" style={{ textAlign: 'center', fontSize: 11 }}>Page {n} of {total}</T>
        </View>
      ))}
      {mine && <Note tone="ok">You signed as {mine.name} on {new Date(mine.signed_at).toLocaleString('en-IN', { day: 'numeric', month: 'short', hour: 'numeric', minute: '2-digit' })}.{theirs ? ` ${theirs.role === 'owner' ? 'The owner' : 'The resident'} signed too.` : ' Waiting for the other side.'}</Note>}
      {canSign && (
        <Card>
          <T v="bodyBold">Sign electronically</T>
          <T v="sm">{broken ? `${broken === 1 ? 'A page' : `${broken} pages`} didn’t load. Load them again above to carry on.` : read < d.pages ? `Read all ${d.pages} pages first (${read} opened so far).` : 'Confirm with the code we send to your phone.'}</T>
          {challenge ? <>
            <T v="sm">Code sent to your phone ending {challenge.last4}.</T>
            <Otp code={challenge.code} onChange={code => setChallenge(x => x && { ...x, code })} />
            <Btn label="Sign the agreement" disabled={busy} onPress={() => act(async () => {
              await ok(api.POST('/api/agreements/{booking_id}/sign', { params: { path: { booking_id: id } }, body: { challenge_id: challenge.id, code: challenge.code, typed_name: '', pages_read: read } }));
              setChallenge(null);
              if (d.my_role === 'tenant') router.back();   // back to Confirm and pay
              else q.reload();
            }, d.my_role === 'tenant' ? 'Signed. Now pay the deposit to book.' : 'Signed.')} />
          </> : <Btn label="Send me the code" disabled={busy || read < d.pages} onPress={() => act(async () => {
            const r = await ok(api.POST('/api/agreements/{booking_id}/sign/start', { params: { path: { booking_id: id } }, body: { pages_read: read } }));
            setChallenge({ id: r.challenge_id, code: r.dev_code ?? '', last4: r.phone_last4 });
          })} />}
          <T v="sm">Your signature records your name as on Aadhaar, the time, this phone and a fingerprint of exactly this document. Neither side can change it later.</T>
        </Card>
      )}
      {d.my_role === 'tenant' && mine && theirs && <Btn label="Back to booking" onPress={() => router.back()} />}
    </Screen>
  );
}
