import type { ReactNode } from 'react';
import { Pressable, View, type StyleProp, type ViewStyle } from 'react-native';
import { T, C, SP } from '@/design';

/* Small pieces the desktop landing page's sections share. */

/* Every section's content: centred, 1120 px at most, 24 px at the sides. */
export const MAX = 1120;
export function Container({ children, style }: { children: ReactNode; style?: StyleProp<ViewStyle> }) {
  return <View style={[{ width: '100%', maxWidth: MAX, alignSelf: 'center', paddingHorizontal: SP.xl }, style]}>{children}</View>;
}

/* A real heading for assistive tech: react-native-web draws role "header" with aria-level as <h1>–<h6>. */
export function Heading({ level, v, children }: { level: 2 | 3; v: 'h2' | 'h3'; children: string }) {
  return <View accessibilityRole="header" aria-level={level}><T v={v}>{children}</T></View>;
}

type PressState = { hovered?: boolean; focused?: boolean };
const FOCUS = { outlineStyle: 'solid', outlineWidth: 2, outlineColor: C.accent, outlineOffset: 2 } as const;

/* A text link: accent text that underlines on hover and shows an outline when reached with the keyboard. */
export function TextLink({ label, onPress, muted }: { label: string; onPress: () => void; muted?: boolean }) {
  return (
    <Pressable onPress={onPress} accessibilityRole="link" accessibilityLabel={label} hitSlop={8}
      style={({ focused }: PressState) => ({ alignSelf: 'flex-start', paddingVertical: 4, borderRadius: 4, ...(focused ? FOCUS : null) })}>
      {({ hovered }: PressState) => <T v="bodyBold" style={{ color: muted ? C.ink : C.accent, textDecorationLine: hovered ? 'underline' : 'none' }}>{label}</T>}
    </Pressable>
  );
}
