import { View } from 'react-native';
import { useWide, Wordmark } from '@/design';
import { useStore } from '@/core/session';
import { AccountMenu } from './AccountMenu';
import { useInOwnerDashboard } from './useInOwnerDashboard';

/* Top bar on the main screens, with the account menu. The side shown follows the account; only the website lets
   an owner switch between their dashboard and the tenant side.
   On a wide website the site header (src/shell/SiteHeader.tsx) carries the logo and the account menu everywhere
   except inside the owner dashboard, so there this bar draws nothing. In the dashboard it keeps only the account
   button, because the sidebar already has the logo. */
export function AppBar() {
  const { s } = useStore();
  const wide = useWide();
  const inDashboard = useInOwnerDashboard();
  if (wide && !inDashboard) return null;
  /* on the wide website the owner's sidebar already carries the logo */
  const sidebar = wide && s.role === 'owner';
  return <AccountMenu left={sidebar ? <View /> : <Wordmark size={28} />} />;
}
