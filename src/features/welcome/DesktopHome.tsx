import { View } from 'react-native';
import { Screen } from '@/design';
import { HomeHero } from './HomeHero';
import { Assurances } from './Assurances';
import { FreeNow } from './FreeNow';
import { HowItWorks } from './HowItWorks';
import { OwnersBand } from './OwnersBand';
import { HomeFooter } from './HomeFooter';

/* The landing page on a wide website. The sections are 72 px apart; each one's content sits in a centred 1120 px
   container, and the owners band and footer run the full width. The footer follows the band directly. */
const GAP = 72;
export function DesktopHome() {
  return (
    <Screen width="full">
      <HomeHero />
      <View style={{ marginTop: GAP }}><Assurances /></View>
      <View style={{ marginTop: GAP }}><FreeNow /></View>
      <View style={{ marginTop: GAP }}><HowItWorks /></View>
      <View style={{ marginTop: GAP }}><OwnersBand /></View>
      <HomeFooter />
    </Screen>
  );
}
