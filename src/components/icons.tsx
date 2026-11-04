import Svg, { Circle, Defs, LinearGradient, Path, Rect, Stop } from 'react-native-svg';
import { View } from 'react-native';
import { C } from '@/lib/theme';
import { T } from './ui';

/* Line icons drawn with SVG so they're pixel-identical on both platforms. */
export type IconName = 'find' | 'stay' | 'req' | 'hist' | 'today' | 'beds' | 'money' | 'people';
export function Icon({ name, color = C.ink, size = 22 }: { name: IconName; color?: string; size?: number }) {
  const p = { fill: 'none', stroke: color, strokeWidth: 1.8, strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const };
  return (
    <Svg width={size} height={size} viewBox="0 0 24 24">
      {name === 'find' && <><Circle cx={11} cy={11} r={6.5} {...p} /><Path d="M16 16l4.5 4.5" {...p} /></>}
      {name === 'stay' && <Path d="M4 20V9l8-5 8 5v11 M9 20v-6h6v6" {...p} />}
      {name === 'req' && <Path d="M14.5 6.5a4 4 0 0 1-5 5L5 16l3 3 4.5-4.5a4 4 0 0 1 5-5l-2.5 2.5-2-2z" {...p} />}
      {name === 'hist' && <><Circle cx={12} cy={12} r={8} {...p} /><Path d="M12 8v4.5l3 2" {...p} /></>}
      {name === 'today' && <><Rect x={4} y={5} width={16} height={15} rx={2.5} {...p} /><Path d="M4 10h16 M9 3v4 M15 3v4" {...p} /></>}
      {name === 'beds' && <Path d="M3 18V8 M3 13h18v5 M7 13V10h5v3" {...p} />}
      {name === 'money' && <><Rect x={3} y={6} width={18} height={12} rx={2.5} {...p} /><Circle cx={12} cy={12} r={2.5} {...p} /></>}
      {name === 'people' && <><Circle cx={9} cy={8} r={3.2} {...p} /><Path d="M3 20c0-3.3 2.7-5.5 6-5.5s6 2.2 6 5.5 M16 5.5a3 3 0 0 1 0 6 M18 14.8c2 .7 3 2.5 3 5.2" {...p} /></>}
    </Svg>
  );
}
/* The mark: a verified home, a house with a tick for a door, on an emerald tile. Same artwork as the app icon. */
export function Logo({ size = 56 }: { size?: number }) {
  return (
    <Svg width={size} height={size} viewBox="0 0 64 64">
      <Defs><LinearGradient id="pk" x1="0" y1="0" x2="1" y2="1"><Stop offset="0" stopColor="#14895F" /><Stop offset="1" stopColor="#0A5640" /></LinearGradient></Defs>
      <Rect width={64} height={64} rx={15} fill="url(#pk)" />
      <Path d="M32 13.5 51 29.2V47a3.5 3.5 0 0 1-3.5 3.5h-31A3.5 3.5 0 0 1 13 47V29.2Z" fill="#FFFFFF" stroke="#FFFFFF" strokeWidth={3} strokeLinejoin="round" />
      <Path d="M24.5 37.8 30 43.2 40.2 33" fill="none" stroke={C.accent} strokeWidth={5.2} strokeLinecap="round" strokeLinejoin="round" />
    </Svg>
  );
}
/* Logo plus wordmark: "pakka" in ink, "ghar" in emerald. */
export function Wordmark({ size = 30 }: { size?: number }) {
  return (
    <View style={{ flexDirection: 'row', alignItems: 'center', gap: size * 0.3 }}>
      <Logo size={size} />
      <T style={{ fontFamily: 'BricolageGrotesque_700Bold', fontSize: size * 0.72, lineHeight: size * 0.9, letterSpacing: -0.6, color: C.ink }}>pakka<T style={{ fontFamily: 'BricolageGrotesque_700Bold', fontSize: size * 0.72, color: C.accent }}>ghar</T></T>
    </View>
  );
}
export function Tick() {
  return <View style={{ width: 56, height: 56, borderRadius: 28, backgroundColor: C.okBg, alignItems: 'center', justifyContent: 'center' }}><T v="h2" style={{ color: C.ok }}>✓</T></View>;
}
export function Bars({ data }: { data: number[] }) {
  const mx = Math.max(...data);
  return <View style={{ flexDirection: 'row', alignItems: 'flex-end', gap: 4, height: 64 }}>{data.map((v, i) => <View key={i} style={{ flex: 1, height: `${Math.round((v / mx) * 100)}%`, backgroundColor: C.accent, opacity: 0.8, borderTopLeftRadius: 3, borderTopRightRadius: 3 }} />)}</View>;
}
