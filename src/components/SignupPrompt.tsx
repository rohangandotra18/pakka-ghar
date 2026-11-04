import { router, type Href } from 'expo-router';
import { AppBar } from './AppBar';
import { Btn, Card, Screen, T } from './ui';

/* Shown on personal tabs while a tenant is only browsing. */
export function SignupPrompt({ title, body, next }: { title: string; body: string; next: Href }) {
  return (
    <Screen>
      <AppBar />
      <Card>
        <T v="h3">{title}</T>
        <T v="sm">{body}</T>
        <Btn label="Sign up free" onPress={() => router.push({ pathname: '/onboarding/tenant', params: { why: 'stay', next: String(next) } })} />
        <Btn kind="ghost" label="Keep browsing" onPress={() => router.replace('/find')} />
      </Card>
    </Screen>
  );
}
