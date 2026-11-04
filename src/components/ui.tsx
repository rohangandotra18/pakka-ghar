import { type ReactNode } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, TextInput, View, type StyleProp, type TextStyle, type ViewStyle } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { router } from 'expo-router';
import { C, F, R, SP } from '@/lib/theme';
import { useStore } from '@/lib/store';

/* Every element is drawn by the app itself (no native switches, sliders or ripples), so iOS and Android match. */
type Variant = 'h1' | 'h2' | 'h3' | 'body' | 'bodyBold' | 'sm' | 'smBold' | 'label' | 'price';
const TV: Record<Variant, TextStyle> = {
  h1: { fontFamily: F.display, fontSize: 28, lineHeight: 33, letterSpacing: -0.6, color: C.ink },
  h2: { fontFamily: F.display, fontSize: 23, lineHeight: 28, letterSpacing: -0.4, color: C.ink },
  h3: { fontFamily: F.display, fontSize: 19, lineHeight: 24, letterSpacing: -0.3, color: C.ink },
  body: { fontFamily: F.regular, fontSize: 15, lineHeight: 22, color: C.ink },
  bodyBold: { fontFamily: F.bold, fontSize: 15, lineHeight: 22, color: C.ink },
  sm: { fontFamily: F.regular, fontSize: 13, lineHeight: 18, color: C.muted },
  smBold: { fontFamily: F.bold, fontSize: 13, lineHeight: 18, color: C.ink },
  label: { fontFamily: F.bold, fontSize: 12, lineHeight: 16, color: C.muted, letterSpacing: 0.2 },
  price: { fontFamily: F.display, fontSize: 19, lineHeight: 24, letterSpacing: -0.3, color: C.ink },
};
export function T({ v = 'body', style, children, numberOfLines }: { v?: Variant; style?: StyleProp<TextStyle>; children: ReactNode; numberOfLines?: number }) {
  return <Text allowFontScaling={false} numberOfLines={numberOfLines} style={[TV[v], { includeFontPadding: false }, style]}>{children}</Text>;
}

export function Screen({ children, scroll = true, pad = true }: { children: ReactNode; scroll?: boolean; pad?: boolean }) {
  const insets = useSafeAreaInsets();
  const { toastMsg } = useStore();
  /* bottom padding clears the home indicator or Android gesture bar on screens without a tab bar */
  const content = <View style={{ gap: SP.md, padding: pad ? SP.lg : 0, paddingBottom: SP.xl * 2 + insets.bottom }}>{children}</View>;
  return (
    <View style={{ flex: 1, backgroundColor: C.bg, paddingTop: insets.top }}>
      {scroll ? <ScrollView keyboardShouldPersistTaps="handled" showsVerticalScrollIndicator={false} overScrollMode="never" bounces={false}>{content}</ScrollView> : content}
      {toastMsg ? <View pointerEvents="none" style={[s.toast, { bottom: 96 + insets.bottom }]}><T v="smBold" style={{ color: C.bg }}>{toastMsg}</T></View> : null}
    </View>
  );
}

export function Btn({ label, onPress, kind = 'primary', small, disabled, style }: { label: string; onPress?: () => void; kind?: 'primary' | 'secondary' | 'ghost'; small?: boolean; disabled?: boolean; style?: StyleProp<ViewStyle> }) {
  const bg = kind === 'primary' ? C.accent : kind === 'secondary' ? C.surface : 'transparent';
  const fg = kind === 'primary' ? C.accentInk : kind === 'ghost' ? C.accent : C.ink;
  return (
    <Pressable accessibilityRole="button" disabled={disabled} onPress={onPress}
      style={({ pressed }) => [s.btn, small && s.btnSm, { backgroundColor: bg, borderColor: kind === 'secondary' ? C.line : bg, opacity: disabled ? 0.45 : pressed ? 0.82 : 1 }, style]}>
      <T v={small ? 'smBold' : 'bodyBold'} style={{ color: fg, textAlign: 'center' }}>{label}</T>
    </Pressable>
  );
}

export function Back({ label = 'Back', onPress }: { label?: string; onPress?: () => void }) {
  return <Pressable accessibilityRole="button" onPress={onPress ?? (() => (router.canGoBack() ? router.back() : router.replace('/')))} hitSlop={10} style={{ alignSelf: 'flex-start', paddingVertical: 4 }}><T v="bodyBold" style={{ color: C.accent }}>‹ {label}</T></Pressable>;
}

export function Card({ children, soft, style }: { children: ReactNode; soft?: boolean; style?: StyleProp<ViewStyle> }) {
  return <View style={[s.card, soft && { backgroundColor: C.accentSoft, borderColor: C.accentSoft }, style]}>{children}</View>;
}

export function Row({ left, right, last }: { left: ReactNode; right?: ReactNode; last?: boolean }) {
  return (
    <View style={[s.row, last && { borderBottomWidth: 0 }]}>
      {typeof left === 'string' ? <T style={{ flex: 1 }}>{left}</T> : <View style={{ flex: 1 }}>{left}</View>}
      {typeof right === 'string' ? <T v="bodyBold">{right}</T> : right}
    </View>
  );
}
export function List({ children }: { children: ReactNode }) { return <View style={s.list}>{children}</View>; }

export function Badge({ label, tone }: { label: string; tone?: 'ok' | 'warn' | 'crit' }) {
  const bg = tone === 'ok' ? C.okBg : tone === 'warn' ? C.warnBg : tone === 'crit' ? C.critBg : C.surface2;
  const fg = tone === 'ok' ? C.ok : tone === 'warn' ? C.warn : tone === 'crit' ? C.crit : C.ink;
  return <View style={[s.badge, { backgroundColor: bg }]}><T v="label" style={{ color: fg, fontSize: 11 }}>{label}</T></View>;
}

export function Chip({ label, on, onPress }: { label: string; on?: boolean; onPress?: () => void }) {
  return <Pressable accessibilityRole="button" accessibilityState={{ selected: !!on }} onPress={onPress} style={[s.chip, on && { backgroundColor: C.ink, borderColor: C.ink }]}><T v="smBold" style={{ color: on ? C.bg : C.ink }}>{label}</T></Pressable>;
}
export function Chips({ children }: { children: ReactNode }) { return <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6 }}>{children}</View>; }

export function Steps({ i, labels }: { i: number; labels: string[] }) {
  return (
    <View style={{ gap: 6 }}>
      <View style={{ flexDirection: 'row', gap: 4 }}>{labels.map((_, k) => <View key={k} style={{ flex: 1, height: 4, borderRadius: 2, backgroundColor: k <= i ? C.accent : C.line }} />)}</View>
      <T v="label">Step {i + 1} of {labels.length} · {labels[i]}</T>
    </View>
  );
}

export function Field({ label, value, placeholder, keyboard }: { label: string; value?: string; placeholder?: string; keyboard?: 'default' | 'number-pad' | 'phone-pad' }) {
  return (
    <View style={{ gap: 5 }}>
      <T v="label">{label}</T>
      <TextInput allowFontScaling={false} defaultValue={value} placeholder={placeholder} placeholderTextColor={C.muted} keyboardType={keyboard}
        style={s.input} underlineColorAndroid="transparent" selectionColor={C.accent} />
    </View>
  );
}

export function Toggle({ on, onChange, label }: { on: boolean; onChange: (v: boolean) => void; label: string }) {
  return (
    <Pressable accessibilityRole="switch" accessibilityState={{ checked: on }} onPress={() => onChange(!on)} style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
      <View style={[s.track, { backgroundColor: on ? C.accent : C.line }]}><View style={[s.thumb, { transform: [{ translateX: on ? 18 : 0 }] }]} /></View>
      <T v="smBold" style={{ flex: 1 }}>{label}</T>
    </Pressable>
  );
}

export function Stars({ value, size = 13 }: { value: number; size?: number }) {
  const n = Math.round(value);
  return <T style={{ fontSize: size, color: C.star, letterSpacing: 1 }}>{'★'.repeat(n)}<T style={{ fontSize: size, color: C.line }}>{'★'.repeat(5 - n)}</T></T>;
}
export function StarInput({ value, onChange }: { value: number; onChange: (n: number) => void }) {
  return (
    <View style={{ flexDirection: 'row', gap: 2 }}>
      {[1, 2, 3, 4, 5].map(n => <Pressable key={n} hitSlop={4} onPress={() => onChange(n)} accessibilityLabel={n + ' stars'}><T style={{ fontSize: 22, color: value >= n ? C.star : C.line }}>★</T></Pressable>)}
    </View>
  );
}

export function Note({ children, tone }: { children: ReactNode; tone?: 'warn' | 'ok' | 'soft' }) {
  const bg = tone === 'ok' ? C.okBg : tone === 'soft' ? C.surface2 : C.warnBg;
  return <View style={{ backgroundColor: bg, borderRadius: R.md, padding: SP.md }}>{typeof children === 'string' ? <T v="sm" style={{ color: C.ink }}>{children}</T> : children}</View>;
}

export function Dot({ color }: { color: string }) { return <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: color }} />; }

export function Hero({ icon, title, body }: { icon: ReactNode; title: string; body: string }) {
  return <View style={{ alignItems: 'center', gap: 10, paddingTop: SP.xl, paddingBottom: SP.md }}>{icon}<T v="h2" style={{ textAlign: 'center' }}>{title}</T><T v="sm" style={{ textAlign: 'center', fontSize: 14, lineHeight: 20 }}>{body}</T></View>;
}

/* A big-number tile for dashboards. */
export function Kpi({ n, t, alert }: { n: string; t: string; alert?: boolean }) {
  return <View style={{ flex: 1, backgroundColor: C.surface, borderRadius: R.md, borderWidth: 1, borderColor: C.line, padding: 12, gap: 2 }}><T v="h2" style={{ color: alert ? C.crit : C.ink }}>{n}</T><T v="sm" style={{ fontSize: 12 }}>{t}</T></View>;
}

export const s = StyleSheet.create({
  btn: { minHeight: 48, paddingHorizontal: 16, borderRadius: 12, alignItems: 'center', justifyContent: 'center', borderWidth: 1 },
  btnSm: { minHeight: 36, paddingHorizontal: 12, borderRadius: 10 },
  card: { backgroundColor: C.surface, borderRadius: R.lg, borderWidth: 1, borderColor: C.line, padding: 14, gap: 8 },
  list: { backgroundColor: C.surface, borderRadius: R.md, borderWidth: 1, borderColor: C.line, overflow: 'hidden' },
  row: { flexDirection: 'row', alignItems: 'center', gap: 10, paddingVertical: 11, paddingHorizontal: 12, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: C.line },
  badge: { borderRadius: R.pill, paddingHorizontal: 8, paddingVertical: 3, alignSelf: 'flex-start' },
  chip: { borderRadius: R.pill, borderWidth: 1, borderColor: C.line, backgroundColor: C.surface, paddingHorizontal: 12, paddingVertical: 7 },
  input: { borderWidth: 1, borderColor: C.line, borderRadius: 11, backgroundColor: C.surface, paddingHorizontal: 12, paddingVertical: 11, fontFamily: F.semi, fontSize: 15, color: C.ink },
  track: { width: 42, height: 24, borderRadius: 12, padding: 3 },
  thumb: { width: 18, height: 18, borderRadius: 9, backgroundColor: '#FFFFFF' },
  toast: { position: 'absolute', left: 16, right: 16, backgroundColor: C.ink, borderRadius: 12, paddingVertical: 12, paddingHorizontal: 14 },
});
