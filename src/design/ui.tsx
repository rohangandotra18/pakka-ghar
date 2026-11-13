import { Children, useEffect, useRef, useState, type ReactNode } from 'react';
import { AccessibilityInfo, ActivityIndicator, Keyboard, Pressable, ScrollView, StyleSheet, Text, TextInput, View, type ScrollViewInstance, type StyleProp, type TextStyle, type ViewStyle, Platform } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { router } from 'expo-router';
import { C, F, R, SP } from './theme';
import { useWide } from './useWide';

/* A short message over the screen, above the tab bar (on a wide website there is no tab bar, so it sits at the
   bottom centre). The shell decides what it says. */
export function Toast({ message }: { message: string }) {
  const insets = useSafeAreaInsets();
  const wide = useWide();
  /* screen readers hear it too: a live region on Android, role=status on the web, and iOS has to be told */
  useEffect(() => { if (message && Platform.OS === 'ios') AccessibilityInfo.announceForAccessibility(message); }, [message]);
  if (!message) return null;
  return <View pointerEvents="none" role="status" accessibilityLiveRegion="polite" style={[s.toast, wide ? { bottom: 24, maxWidth: 420, marginHorizontal: 'auto' } : { bottom: 96 + insets.bottom }]}><T v="smBold" style={{ color: C.bg }}>{message}</T></View>;
}

/* Every element is drawn by the app itself (no native switches, sliders or ripples), so iOS and Android match. */
type Variant = 'display' | 'h1' | 'h2' | 'h3' | 'body' | 'bodyBold' | 'sm' | 'smBold' | 'label' | 'price';
const TV: Record<Variant, TextStyle> = {
  /* the big title of a page on a wide screen; phones keep h1 */
  display: { fontFamily: F.display, fontSize: 44, lineHeight: 50, letterSpacing: -1, color: C.ink },
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
export function T({ v = 'body', style, children, numberOfLines, accessibilityLabel }: { v?: Variant; style?: StyleProp<TextStyle>; children: ReactNode; numberOfLines?: number; accessibilityLabel?: string }) {
  return <Text allowFontScaling={false} numberOfLines={numberOfLines} accessibilityLabel={accessibilityLabel} style={[TV[v], { includeFontPadding: false }, style]}>{children}</Text>;
}

/* The page. `width` sets how wide its content may be on a wide website (phones and narrow windows ignore it):
     'text' (default)  a 760 px centred column, for forms and reading
     'wide'            a 1120 px centred column with 24 px side padding, for pages with two columns or a grid
     'full'            no maximum width and no padding, for pages that lay out their own panes. With scroll={false} the
                       content also fills the height left under the header (flex: 1, no gap, no bottom padding), so
                       a pane can be exactly as tall as the window.
   <Screen width="wide"> ... </Screen> */
export type ScreenWidth = 'text' | 'wide' | 'full';
export function Screen({ children, scroll = true, pad = true, width = 'text' }: { children: ReactNode; scroll?: boolean; pad?: boolean; width?: ScreenWidth }) {
  const wide = useWide();
  const insets = useSafeAreaInsets();
  const scrollRef = useRef<ScrollViewInstance>(null);
  /* Neither platform makes room for the keyboard here (Android is edge-to-edge), so we add a spacer the
     keyboard's height under the content, then scroll the focused field up. Same behaviour on both. */
  const [kb, setKb] = useState(0);
  useEffect(() => {
    if (!scroll) return;
    const show = Keyboard.addListener('keyboardDidShow', e => {
      setKb(e.endCoordinates.height);
      /* wait a frame for the spacer, then bring the field near the top with room for the button under it */
      requestAnimationFrame(() => {
        const input = TextInput.State.currentlyFocusedInput();
        const sv = scrollRef.current, inner = sv?.getInnerViewRef();
        if (!input || !sv || !inner) return;
        input.measureLayout(inner, (_x, y) => sv.scrollTo({ y: Math.max(0, y - 96), animated: true }), () => {});
      });
    });
    const hide = Keyboard.addListener('keyboardDidHide', () => setKb(0));
    return () => { show.remove(); hide.remove(); };
  }, [scroll]);
  /* bottom padding clears the home indicator or Android gesture bar, or the keyboard when it's open */
  /* on the website the same screens sit in a centred, readable column */
  const column: ViewStyle | null = Platform.OS !== 'web' ? null
    : wide && width === 'wide' ? { width: '100%', maxWidth: 1120, alignSelf: 'center', ...(pad ? { paddingHorizontal: SP.xl } : null) }
    : wide && width === 'full' ? { width: '100%', padding: 0 }
    : { width: '100%', maxWidth: 760, alignSelf: 'center' };
  const fills = wide && width === 'full' && !scroll;
  const content = <View style={{ gap: SP.md, padding: pad ? SP.lg : 0, paddingBottom: SP.xl * 2 + (kb || insets.bottom), ...column, ...(fills ? { flex: 1, gap: 0, paddingBottom: 0, minHeight: 0 } : null) }}>{children}</View>;
  return (
    <View style={{ flex: 1, backgroundColor: C.bg, paddingTop: insets.top }}>
      {scroll ? <ScrollView ref={scrollRef} keyboardShouldPersistTaps="handled" keyboardDismissMode="on-drag" showsVerticalScrollIndicator={false} overScrollMode="never" bounces={false}>{content}</ScrollView> : content}
    </View>
  );
}

/* Main content with a side panel, for wide pages. On a wide website `children` and `side` sit in two columns and the
   side column stays in view (sticks to the top of the page area) while the main column scrolls. On phones and in a
   narrow window the main content comes first and the side content follows, stacked.
   <Columns side={<Card>...</Card>} sideWidth={360} gap={32}>{main}</Columns> */
/* RN's style types have no `position: 'sticky'`, but react-native-web passes it to CSS, so this is the one cast. */
const STICKY = { position: 'sticky', top: SP.xl, alignSelf: 'flex-start' } as unknown as ViewStyle;
export function Columns({ children, side, sideWidth = 360, gap = 32 }: { children: ReactNode; side: ReactNode; sideWidth?: number; gap?: number }) {
  const wide = useWide();
  if (!wide) return <View style={{ gap: SP.md }}>{children}{side}</View>;
  return (
    <View style={{ flexDirection: 'row', alignItems: 'flex-start', gap }}>
      <View style={{ flex: 1, minWidth: 0, gap: SP.md }}>{children}</View>
      <View style={[{ width: sideWidth, gap: SP.md }, STICKY]}>{side}</View>
    </View>
  );
}

/* When onPress returns a promise (an `act(...)` call does), the pressed button shows a spinner until it settles, so
   of all the buttons a busy screen greys out, the one you tapped is the one that looks at work. */
export function Btn({ label, onPress, kind = 'primary', small, disabled, style }: { label: string; onPress?: () => unknown; kind?: 'primary' | 'secondary' | 'ghost'; small?: boolean; disabled?: boolean; style?: StyleProp<ViewStyle> }) {
  const bg = kind === 'primary' ? C.accent : kind === 'secondary' ? C.surface : 'transparent';
  const fg = kind === 'primary' ? C.accentInk : kind === 'ghost' ? C.accent : C.ink;
  const [working, setWorking] = useState(false);
  const press = () => {
    const r = onPress?.();
    if (r instanceof Promise) {
      setWorking(true);
      r.finally(() => setWorking(false)).catch(() => {});
    }
  };
  return (
    <Pressable accessibilityRole="button" accessibilityState={{ disabled: !!disabled || working, busy: working }} disabled={disabled || working} onPress={press}
      style={({ pressed }) => [s.btn, small && s.btnSm, { backgroundColor: bg, borderColor: kind === 'secondary' ? C.line : bg, opacity: disabled && !working ? 0.45 : pressed ? 0.82 : 1 }, style]}>
      {/* the label stays, invisibly, so the button keeps its size */}
      <T v={small ? 'smBold' : 'bodyBold'} style={{ color: fg, textAlign: 'center', opacity: working ? 0 : 1 }}>{label}</T>
      {working && <ActivityIndicator color={fg} style={StyleSheet.absoluteFill} accessibilityLabel="Working" />}
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

export function Chip({ label, on, onPress }: { label: string; on?: boolean; onPress?: () => unknown }) {
  /* Used as an action too (bids, instant booking): like Btn, while its promise runs it shows a spinner and takes no
     second tap, so a quick double tap can't switch something on and straight off again. */
  const [working, setWorking] = useState(false);
  const press = () => {
    const r = onPress?.();
    if (r instanceof Promise) {
      setWorking(true);
      r.finally(() => setWorking(false)).catch(() => {});
    }
  };
  const fg = on ? C.bg : C.ink;
  /* a little extra to tap above and below: chips wrap onto rows only 6pt apart, so not enough to overlap the next row */
  return <Pressable accessibilityRole="button" accessibilityState={{ selected: !!on, disabled: working, busy: working }} disabled={working} onPress={press} hitSlop={{ top: 3, bottom: 3 }}
    style={({ pressed }) => [s.chip, on && { backgroundColor: C.ink, borderColor: C.ink }, { opacity: pressed ? 0.75 : 1 }]}>
    <T v="smBold" style={{ color: fg, opacity: working ? 0 : 1 }}>{label}</T>
    {working && <ActivityIndicator size="small" color={fg} style={StyleSheet.absoluteFill} accessibilityLabel="Working" />}
  </Pressable>;
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

/* Pass onChangeText to make it controlled (the value is what gets sent); without it, value is just a starting text. */
export function Field({ label, value, placeholder, keyboard, multiline, maxLength, onChangeText }: { label: string; value?: string; placeholder?: string; keyboard?: 'default' | 'number-pad' | 'phone-pad'; multiline?: boolean; maxLength?: number; onChangeText?: (t: string) => void }) {
  const [focused, setFocused] = useState(false);
  /* a limit is only worth showing once it's close: from 80% of it */
  const used = value?.length ?? 0;
  const near = maxLength != null && onChangeText != null && used >= maxLength * 0.8;
  return (
    <View style={{ gap: 5 }}>
      <T v="label">{label}</T>
      <TextInput accessibilityLabel={label} allowFontScaling={false} {...(onChangeText ? { value, onChangeText } : { defaultValue: value })} placeholder={placeholder} placeholderTextColor={C.muted} keyboardType={keyboard} maxLength={maxLength}
        multiline={multiline} textAlignVertical={multiline ? 'top' : undefined} onFocus={() => setFocused(true)} onBlur={() => setFocused(false)}
        style={[s.input, multiline && { minHeight: 84 }, focused && { borderColor: C.accent }]} underlineColorAndroid="transparent" selectionColor={C.accent} />
      {near && <T v="sm" style={{ alignSelf: 'flex-end', fontSize: 12, color: used >= maxLength ? C.warn : C.muted }}>{used} / {maxLength}</T>}
    </View>
  );
}

export function Toggle({ on, onChange, label }: { on: boolean; onChange: (v: boolean) => void; label: string }) {
  return (
    <Pressable accessibilityRole="switch" accessibilityState={{ checked: on }} accessibilityLabel={label} onPress={() => onChange(!on)} hitSlop={{ top: 10, bottom: 10 }}
      style={({ pressed }) => ({ flexDirection: 'row', alignItems: 'center', gap: 10, opacity: pressed ? 0.75 : 1 })}>
      <View style={[s.track, { backgroundColor: on ? C.accent : C.line }]}><View style={[s.thumb, { transform: [{ translateX: on ? 18 : 0 }] }]} /></View>
      <T v="smBold" style={{ flex: 1 }}>{label}</T>
    </Pressable>
  );
}

export function Stars({ value, size = 13 }: { value: number; size?: number }) {
  const n = Math.round(value);
  return <T accessibilityLabel={`${n} out of 5 stars`} style={{ fontSize: size, color: C.star, letterSpacing: 1 }}>{'★'.repeat(n)}<T style={{ fontSize: size, color: C.line }}>{'★'.repeat(5 - n)}</T></T>;
}
export function StarInput({ value, onChange }: { value: number; onChange: (n: number) => void }) {
  return (
    <View style={{ flexDirection: 'row' }}>
      {/* 36pt targets with slop, so each star is easy to hit and screen readers announce it */}
      {[1, 2, 3, 4, 5].map(n => <Pressable key={n} hitSlop={6} onPress={() => onChange(n)} accessibilityRole="button" accessibilityLabel={`${n} star${n > 1 ? 's' : ''}`} accessibilityState={{ selected: value >= n }} style={{ width: 30, height: 36, alignItems: 'center', justifyContent: 'center' }}><T style={{ fontSize: 24, lineHeight: 30, color: value >= n ? C.star : C.line }}>★</T></Pressable>)}
    </View>
  );
}

export function Note({ children, tone }: { children: ReactNode; tone?: 'warn' | 'ok' | 'soft' }) {
  const bg = tone === 'ok' ? C.okBg : tone === 'soft' ? C.surface2 : C.warnBg;
  /* plain text, including text with {values} in it, goes in a T; anything else is laid out as given */
  const textOnly = Children.toArray(children).every(c => typeof c === 'string' || typeof c === 'number');
  return <View style={{ backgroundColor: bg, borderRadius: R.md, padding: SP.md }}>{textOnly ? <T v="sm" style={{ color: C.ink }}>{children}</T> : children}</View>;
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
