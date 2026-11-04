import { router } from 'expo-router';
import { Pressable, View } from 'react-native';
import { AppBar } from '@/components/AppBar';
import { Card, Screen, T } from '@/components/ui';
import { OFFERS } from '@/lib/data';
import { useStore } from '@/lib/store';
import { C } from '@/lib/theme';

type Bed = { who?: string; tag?: 'leaving' | 'new' | 'offers' };
export default function Beds() {
  const { s } = useStore();
  const rooms: [string, Bed[]][] = [
    ['101', [{ who: 'Aman' }, { who: 'Rohit' }]],
    ['102', [{ who: 'Harsh' }, { who: 'Karanveer' }]],
    ['103', [{ who: 'Nikhil' }, { who: 'Yash' }, { who: 'Arjun' }]],
    ['104', [{ who: 'Sahil', tag: 'leaving' }, { who: 'Ishaan' }, s.acceptedOffer ? { who: s.acceptedOffer.split(' ')[0], tag: 'new' } : { tag: 'offers' }]],
  ];
  return (
    <Screen>
      <AppBar />
      <T v="h2">Bed board</T>
      <T v="sm">3 beds free. Demand in Sector 15 is high, so offers are open on free beds.</T>
      {rooms.map(([no, beds]) => (
        <Card key={no}>
          <T v="smBold">Room {no}</T>
          <View style={{ flexDirection: 'row', gap: 6 }}>
            {beds.map((b, i) => {
              const free = !b.who;
              const bg = free ? C.okBg : b.tag === 'leaving' ? C.warnBg : b.tag === 'new' ? C.surface2 : C.accentSoft;
              const cell = (
                <View style={{ flex: 1, minHeight: 52, borderRadius: 10, padding: 8, backgroundColor: bg, borderWidth: free ? 1 : 0, borderColor: C.ok, borderStyle: 'dashed' }}>
                  <T v="smBold" style={{ fontSize: 12, color: free ? C.ok : C.ink }}>{b.who ?? `Bed ${i + 1}`}</T>
                  <T v="sm" style={{ fontSize: 11 }}>{free ? (s.offersOpen ? `${OFFERS.length} offers` : 'Free') : b.tag === 'leaving' ? 'leaves 22 Nov' : b.tag === 'new' ? 'from 1 Dec' : ' '}</T>
                </View>
              );
              return free ? <Pressable key={i} style={{ flex: 1 }} onPress={() => router.push('/offers')}>{cell}</Pressable> : <View key={i} style={{ flex: 1 }}>{cell}</View>;
            })}
          </View>
        </Card>
      ))}
    </Screen>
  );
}
