import { useState } from 'react';
import { router } from 'expo-router';
import { TextInput, View } from 'react-native';
import { Back, Btn, Chip, Chips, Note, Screen, T } from '@/components/ui';
import { REQUEST_CATEGORIES } from '@/lib/data';
import { useStore } from '@/lib/store';
import { C, F } from '@/lib/theme';

const DEFAULT_TEXT: Record<string, string> = {
  'Listing issue': 'The listing says AC rooms, but my room has only a cooler.',
  'Asked to pay in cash': "The warden asked me to pay this month's rent in cash.",
};
export default function NewRequest() {
  const { s, set, toast } = useStore();
  const cats = s.stay ? REQUEST_CATEGORIES : ['Listing issue', 'Asked to pay in cash'];
  const [cat, setCat] = useState(cats[0]);
  const cash = cat === 'Asked to pay in cash';
  const text = DEFAULT_TEXT[cat] ?? 'Bathroom tap keeps leaking.';
  return (
    <Screen>
      <Back />
      <T v="h2">New request</T>
      <T v="label">What’s it about?</T>
      <Chips>{cats.map(c => <Chip key={c} label={c} on={cat === c} onPress={() => setCat(c)} />)}</Chips>
      <T v="label">Describe it</T>
      <TextInput key={cat} allowFontScaling={false} multiline defaultValue={text} style={{ minHeight: 90, borderWidth: 1, borderColor: C.line, borderRadius: 11, backgroundColor: C.surface, padding: 12, fontFamily: F.semi, fontSize: 15, color: C.ink, textAlignVertical: 'top' }} />
      {!cash && <View style={{ borderWidth: 1.5, borderStyle: 'dashed', borderColor: C.line, borderRadius: 12, padding: 18, alignItems: 'center' }}><T v="smBold" style={{ color: C.muted }}>+ Add photo</T></View>}
      <Note tone="soft">{cash ? "This goes to Pakka Ghar only, not the owner. Don't pay cash: it won't count as rent and isn't protected." : cat === 'Listing issue' ? 'Listing issues go to Pakka Ghar as well as the owner.' : 'The owner sees it at once and can assign someone.'}</Note>
      <Btn label={cash ? 'Report to Pakka Ghar' : 'Send request'} onPress={() => {
        set({ myRequests: [{ id: 'R-' + (220 + s.myRequests.length), who: 'You', room: s.stay?.room ?? '–', cat, text: cash ? 'Asked to pay rent in cash' : text, status: 'Raised', at: 'Now', to: cash ? 'Pakka Ghar trust team' : undefined }, ...s.myRequests] });
        toast(cash ? "Reported. We'll contact the owner within a day." : 'Request sent to the owner.');
        router.back();
      }} />
    </Screen>
  );
}
