import { ActivityIndicator, View } from 'react-native';
import type { ApiError } from '@/api/client';
import { C } from '@/lib/theme';
import { Btn, Card, T } from './ui';

/* What a screen shows before its data arrives, or when it can't be loaded. */
export function Loading({ error, retry }: { error?: ApiError | null; retry?: () => void }) {
  if (error) return (
    <Card>
      <T v="bodyBold">{error.code === 'offline' ? 'No connection' : "Couldn't load this"}</T>
      <T v="sm">{error.message}</T>
      {retry && <Btn small kind="secondary" label="Try again" onPress={retry} />}
    </Card>
  );
  return <View style={{ paddingVertical: 40, alignItems: 'center' }}><ActivityIndicator color={C.accent} /></View>;
}
