import { router } from 'expo-router';
import { AppBar } from './AppBar';
import { Btn, Card, Screen, T } from './ui';

/* Shown on personal tabs while a tenant is only browsing. */
export function SignupPrompt({ title, body }: { title: string; body: string }) {
  return (
    <Screen>
      <AppBar />
      <Card>
        <T v="h3">{title}</T>
        <T v="sm">{body}</T>
        <Btn label="Sign up free" onPress={() => router.push({ pathname: '/onboarding/tenant', params: { why: 'stay' } })} />
        <Btn kind="ghost" label="Keep browsing" onPress={() => router.replace('/find')} />
      </Card>
    </Screen>
  );
}
