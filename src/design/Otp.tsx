import { View } from 'react-native';
import { C, R } from './theme';
import { T } from './ui';

/* The six code boxes shown after a mobile number is entered. */
export function Otp({ code }: { code: string }) {
  return (
    <View style={{ flexDirection: 'row', gap: 6, justifyContent: 'center' }}>
      {code.split('').map((c, k) => <View key={k} style={{ width: 42, height: 50, borderRadius: R.sm, borderWidth: 1, borderColor: C.line, backgroundColor: C.surface, alignItems: 'center', justifyContent: 'center' }}><T v="h3">{c}</T></View>)}
    </View>
  );
}
