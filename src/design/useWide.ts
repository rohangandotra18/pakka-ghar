import { Platform, useWindowDimensions } from 'react-native';

/* The width, in px, from which the website switches to its desktop layout. */
export const WIDE_MIN = 900;

/* True on the website when the window is at least WIDE_MIN px wide ("wide"). Always false on iOS and Android and
   in a narrow browser window, so anything that only happens `if (wide)` can never change the phone layout.
   It follows the window as it is resized.
     const wide = useWide();
     return wide ? <SideBySide /> : <Stacked />; */
export function useWide(): boolean {
  const { width } = useWindowDimensions();
  return Platform.OS === 'web' && width >= WIDE_MIN;
}
