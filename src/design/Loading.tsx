import { ActivityIndicator, View } from 'react-native';
import { C } from './theme';
import { Btn, Card, T } from './ui';

/* What a screen shows before its data arrives, or when it can't be loaded. */
export function Loading({ error, retry }: { error?: { code?: string; message: string } | null; retry?: () => void }) {
  if (error) return (
    <View role="alert" accessibilityLiveRegion="assertive">
      <Card>
        <T v="bodyBold">{error.code === 'offline' ? 'No connection' : "Couldn't load this"}</T>
        <T v="sm">{error.message}</T>
        {retry && <Btn small kind="secondary" label="Try again" onPress={retry} />}
      </Card>
    </View>
  );
  return <View style={{ paddingVertical: 40, alignItems: 'center' }}><ActivityIndicator color={C.accent} accessibilityLabel="Loading" /></View>;
}
