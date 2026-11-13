import { useState } from 'react';
import { router } from 'expo-router';
import { Image, Pressable, View } from 'react-native';
import { Back, Btn, Chip, Chips, Field, Note, Screen, T, C } from '@/design';
import { api, ok, useAction, useQuery } from '@/core/api';
import { takeOnSitePhoto, uploadShot, type OnSiteShot } from '@/core/device';
import { useStore } from '@/core/session';

const REQUEST_CATEGORIES = ['Electrical', 'Plumbing', 'Wi-Fi', 'Cleaning', 'Furniture', 'Listing issue', 'Asked to pay in cash'];

/* examples shown as placeholders, never sent */
const DEFAULT_TEXT: Record<string, string> = {
  'Listing issue': 'The listing says AC rooms, but my room has only a cooler.',
  'Asked to pay in cash': "The warden asked me to pay this month's rent in cash.",
};
/* someone who hasn't moved in yet reports what they saw, not their own room */
const VISITOR_TEXT: Record<string, string> = {
  'Listing issue': "The photos don't match the PG I visited: the rooms are smaller.",
  'Asked to pay in cash': 'The owner asked for the deposit in cash when I visited.',
};
export default function NewRequest() {
  const { act, busy } = useAction();
  const { toast } = useStore();
  const q = useQuery(() => ok(api.GET('/api/stay')));
  /* repairs need someone living there; anyone can report a listing or a cash request */
  const living = !!q.data?.stay?.moved_in;
  const cats = living ? REQUEST_CATEGORIES : ['Listing issue', 'Asked to pay in cash'];
  const [chosen, setCat] = useState<string | null>(null);
  const cat = chosen && cats.includes(chosen) ? chosen : cats[0];
  const starter = (c: string) => (living ? DEFAULT_TEXT[c] ?? 'Bathroom tap keeps leaking.' : VISITOR_TEXT[c]);
  /* what the tenant types is what gets sent; the example for the category shows as a placeholder */
  const [text, setText] = useState('');
  const cash = cat === 'Asked to pay in cash';
  /* a photo of the problem, taken now in the room with the camera (never from the gallery) */
  const [shot, setShot] = useState<OnSiteShot | null>(null);
  const snap = async () => { try { setShot(await takeOnSitePhoto()); } catch (e) { toast(e instanceof Error ? e.message : 'Camera unavailable'); } };
  /* with no stay there's no owner to send to yet, so it goes to Pakka Ghar */
  const toUs = cash || !living;
  return (
    <Screen>
      <Back />
      <T v="h2">{living ? 'New request' : 'Report a problem'}</T>
      <T v="label">What’s it about?</T>
      <Chips>{cats.map(c => <Chip key={c} label={c} on={cat === c} onPress={() => setCat(c)} />)}</Chips>
      <Field label="Describe it" multiline value={text} onChangeText={setText} placeholder={starter(cat)} />
      {living && !toUs && (shot
        ? <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}><Image source={{ uri: shot.uri }} style={{ width: 72, height: 72, borderRadius: 10 }} accessibilityLabel="Your photo" /><Btn small kind="ghost" label="Retake" onPress={snap} /></View>
        : <Pressable onPress={snap} accessibilityRole="button" style={{ borderWidth: 1.5, borderStyle: 'dashed', borderColor: C.line, borderRadius: 12, padding: 18, alignItems: 'center' }}><T v="smBold" style={{ color: C.muted }}>+ Take a photo of it</T></Pressable>)}
      <Note tone="soft">{cash ? "This goes to Pakka Ghar only, not the owner. Don't pay cash: it won't count as rent and isn't protected." : !living ? 'This goes to the Pakka Ghar trust team, who check the listing with the owner.' : cat === 'Listing issue' ? 'Listing issues go to Pakka Ghar as well as the owner.' : 'The owner sees it at once and can assign someone.'}</Note>
      <Btn label={toUs ? 'Report to Pakka Ghar' : 'Send request'} disabled={!text.trim() || busy} onPress={() => act(async () => {
        const t = await ok(api.POST('/api/requests', { body: { category: cat, text: text.trim() } }));
        if (shot && !t.to_pakka_ghar) await uploadShot(`/api/requests/${t.id}/photos`, shot).catch(e => toast(e.message));
        router.back();
      }, toUs ? "Reported. We'll look into it within a day." : 'Request sent to the owner.')} />
    </Screen>
  );
}
