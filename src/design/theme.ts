/* One palette and one type scale for both platforms. No platform shadows: iOS shadows and Android
   elevation render differently, so surfaces are separated with hairline borders and tints instead. */
export const C = {
  bg: '#F5F7F5',
  surface: '#FFFFFF',
  surface2: '#EEF2EF',
  ink: '#111714',
  muted: '#5D6862',
  line: '#E2E7E3',
  accent: '#0E6B50',
  accentDeep: '#0A5640',
  accentInk: '#FFFFFF',
  accentSoft: '#E2F1EA',
  ok: '#1E7B47',
  okBg: '#E1F3E7',
  warn: '#935F00',
  warnBg: '#FBF0D8',
  crit: '#B42318',
  critBg: '#FDE8E5',
  boys: '#2C6ECB',
  girls: '#C2417F',
  coed: '#0E8A7E',
  star: '#E2A100',
  map: '#EEF1EC',
  mapRoad: '#FFFFFF',
  mapPark: '#D9EAD2',
  mapWater: '#C3DDEC',
};

export const F = {
  display: 'BricolageGrotesque_700Bold',
  displaySemi: 'BricolageGrotesque_600SemiBold',
  regular: 'Manrope_500Medium',
  semi: 'Manrope_600SemiBold',
  bold: 'Manrope_700Bold',
  black: 'Manrope_800ExtraBold',
};

export const R = { sm: 10, md: 14, lg: 18, pill: 999 };
export const SP = { xs: 4, sm: 8, md: 12, lg: 16, xl: 24 };

export const GENDER_COLOR: Record<string, string> = { Boys: C.boys, Girls: C.girls, 'Co-ed': C.coed };

export const rupees = (v: number) => '₹' + Math.round(v).toLocaleString('en-IN');
