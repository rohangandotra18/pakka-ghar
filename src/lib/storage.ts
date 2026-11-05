import { Platform } from 'react-native';
import * as SecureStore from 'expo-secure-store';

/* Where a signed-in session is kept: the phone's keychain/keystore, or the browser's local storage on the website.
   (On the web the session is as safe as the site: keep it free of third-party scripts.) */
const web = Platform.OS === 'web';

export async function getItem(key: string): Promise<string | null> {
  if (web) { try { return globalThis.localStorage?.getItem(key) ?? null; } catch { return null; } }
  return SecureStore.getItemAsync(key);
}
export async function setItem(key: string, value: string): Promise<void> {
  if (web) { try { globalThis.localStorage?.setItem(key, value); } catch { /* private mode */ } return; }
  await SecureStore.setItemAsync(key, value);
}
export async function deleteItem(key: string): Promise<void> {
  if (web) { try { globalThis.localStorage?.removeItem(key); } catch { /* private mode */ } return; }
  await SecureStore.deleteItemAsync(key);
}
