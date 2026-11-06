import Constants from 'expo-constants';
import createClient, { type Middleware } from 'openapi-fetch';
import type { components, paths } from './schema';

/* The typed client for the Pakka Ghar API. Its types are generated from contracts/openapi.json
   (export_openapi, then npm run api:types), so a backend change that breaks the app fails the typecheck. */

/* The API's origin (paths in the contract start with /api). In development the API runs on the same machine as Metro: reuse Metro's host so a phone on the same Wi-Fi works.
   On the Android emulator Metro is 127.0.0.1 through `adb reverse`, so reverse port 8000 too. */
function apiBase() {
  const fromEnv = process.env.EXPO_PUBLIC_API_URL;
  if (fromEnv) return fromEnv.replace(/\/$/, '');
  if (typeof window !== 'undefined' && window.location?.hostname && !Constants.expoConfig?.hostUri) {
    return `${window.location.protocol}//${window.location.hostname}:8000`;   // the website: API on the same host
  }
  const host = Constants.expoConfig?.hostUri?.split(':')[0] ?? 'localhost';
  return `http://${host}:8000`;
}
export const API_BASE = apiBase();

export type Schemas = components['schemas'];

/* Set by the session store: the token for whichever side (tenant or owner) is on screen. */
let currentToken: string | null = null;
export function setToken(t: string | null) { currentToken = t; }
export function getToken() { return currentToken; }
/* Set by the session store: told when the server refuses a token (signed out on another device, account closed),
   so the app drops that sign-in instead of failing every request. */
let unauthorized: ((token: string) => void) | null = null;
export function onUnauthorized(cb: ((token: string) => void) | null) { unauthorized = cb; }
export function tokenRefused(token: string) { unauthorized?.(token); }

const auth: Middleware = {
  onRequest({ request }) {
    if (currentToken && !request.headers.has('Authorization')) request.headers.set('Authorization', `Bearer ${currentToken}`);
    return request;
  },
  onResponse({ request, response }) {
    const sent = request.headers.get('Authorization')?.replace(/^Bearer /, '');
    if (response.status === 401 && sent) tokenRefused(sent);
    /* returns nothing: openapi-fetch keeps the response as it is (React Native's isn't a `Response` it accepts back) */
  },
};

export const api = createClient<paths>({ baseUrl: API_BASE });
api.use(auth);

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string) { super(message); }
}

/* Unwrap an openapi-fetch result: return the data or throw an ApiError with the server's message. */
export async function ok<T>(p: Promise<{ data?: T; error?: unknown; response: Response }>): Promise<T> {
  let r: { data?: T; error?: unknown; response: Response };
  try {
    r = await p;
  } catch {
    throw new ApiError(0, 'offline', "Can't reach Pakka Ghar. Check your connection.");
  }
  if (r.response.ok) return r.data as T;
  const e = (r.error ?? {}) as { code?: string; message?: string; detail?: unknown };
  /* the API's own errors carry a message; request validation errors (422) carry a detail list */
  const msg = e.message ?? (r.response.status === 401 ? 'Please sign in again.'
    : Array.isArray(e.detail) ? 'Check the details you entered.' : 'Something went wrong. Try again.');
  throw new ApiError(r.response.status, e.code ?? String(r.response.status), msg);
}

/* One key per user action, so a retried tap never books or pays twice. */
export const newKey = () => `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
export const idem = (key = newKey()) => ({ headers: { 'Idempotency-Key': key } });

/* Money is integer paise everywhere in the API. */
export const inr = (paise: number | null | undefined) => '₹' + Math.round((paise ?? 0) / 100).toLocaleString('en-IN');
export const rupeesOf = (paise: number) => Math.round(paise / 100);

/* File uploads (multipart). Expo's fetch rejects React Native's { uri, name, type } file parts, while React Native's
   XMLHttpRequest streams them from disk, so uploads go through XHR. */
export function postFile(path: string, file: { uri: string; name: string; type: string; webFile?: Blob }, fields: Record<string, string> = {}): Promise<Record<string, unknown>> {
  return new Promise((resolve, reject) => {
    const form = new FormData();
    if (file.webFile) form.append('file', file.webFile, file.name);   // website: the browser's File
    else form.append('file', file as unknown as Blob);                // phone: streamed from disk by uri
    for (const [k, v] of Object.entries(fields)) form.append(k, v);
    const x = new XMLHttpRequest();
    x.open('POST', `${API_BASE}${path}`);
    if (currentToken) x.setRequestHeader('Authorization', `Bearer ${currentToken}`);
    x.onload = () => {
      let body: Record<string, unknown> = {};
      try { body = JSON.parse(x.responseText); } catch { /* not JSON */ }
      if (x.status >= 200 && x.status < 300) resolve(body);
      else reject(new ApiError(x.status, String(body.code ?? x.status), String(body.message ?? 'The upload failed.')));
    };
    x.onerror = () => reject(new ApiError(0, 'offline', "Can't reach Pakka Ghar. Check your connection."));
    x.send(form);
  });
}
