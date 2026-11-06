import { Platform } from 'react-native';
import * as ImagePicker from 'expo-image-picker';
import * as Location from 'expo-location';
import { API_BASE, ApiError, postFile } from '../api/client';

/* Photos come only from the camera, at the place, right now. There is no gallery picker anywhere in the app:
   the server also refuses photos taken elsewhere, more than ten minutes ago, or by editing or AI software. */
export type OnSiteShot = { uri: string; takenAt: string; lat: number; lng: number; accuracy: number };

export async function takeOnSitePhoto(): Promise<OnSiteShot | null> {
  /* a browser can't prove where or when a picture was taken, so photos are only ever taken in the phone app */
  if (Platform.OS === 'web') throw new ApiError(0, 'phone_only', 'Photos are taken with the Pakka Ghar app on your phone, at the building.');
  const cam = await ImagePicker.requestCameraPermissionsAsync();
  if (!cam.granted) throw new ApiError(0, 'camera', 'Allow the camera to take photos.');
  const loc = await Location.requestForegroundPermissionsAsync();
  if (!loc.granted) throw new ApiError(0, 'location', 'Allow location so we can check the photo is taken at the building.');
  if (!(await Location.hasServicesEnabledAsync())) throw new ApiError(0, 'location_off', 'Turn on location in your phone’s settings, then try again.');
  /* start the GPS fix while the camera is open; a failure is handled below, never left unhandled */
  const fix = Promise.race([
    Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.High }).catch(() => null),
    new Promise<null>(r => setTimeout(() => r(null), 12000)),   // never wait forever for a GPS fix
  ]);
  const shot = await ImagePicker.launchCameraAsync({ mediaTypes: ['images'], quality: 0.75, allowsEditing: false, exif: false });
  if (shot.canceled || !shot.assets?.[0]) return null;
  const takenAt = new Date().toISOString();
  const p = (await fix) ?? (await Location.getLastKnownPositionAsync({ maxAge: 120000, requiredAccuracy: 200 }).catch(() => null));
  if (!p) throw new ApiError(0, 'no_location', 'Couldn’t get your location. Step near a window or outside, wait a moment and try again.');
  return { uri: shot.assets[0].uri, takenAt, lat: p.coords.latitude, lng: p.coords.longitude, accuracy: p.coords.accuracy ?? 999 };
}

/* Upload a shot with its time and place; the server re-checks both. */
export async function uploadShot(path: string, shot: OnSiteShot, fields: Record<string, string> = {}) {
  const body = await postFile(path, { uri: shot.uri, name: 'photo.jpg', type: 'image/jpeg' }, {
    taken_at: shot.takenAt, lat: String(shot.lat), lng: String(shot.lng), accuracy_m: String(Math.round(shot.accuracy)), ...fields,
  });
  return body as { id: string; url: string; thumb: string };
}

/* Photo paths from the API are relative to the server. */
export const mediaUrl = (path: string) => (path.startsWith('http') ? path : `${API_BASE}${path}`);

/* Where the phone is right now, for pinning a building while standing at it. */
export async function whereAmI(): Promise<{ lat: number; lng: number } | null> {
  const loc = await Location.requestForegroundPermissionsAsync();
  if (!loc.granted) throw new ApiError(0, 'location', 'Allow location to pin the building from where you’re standing.');
  const p = await Promise.race([
    Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.High }).catch(() => null),
    new Promise<null>(r => setTimeout(() => r(null), 12000)),
  ]);
  return p ? { lat: p.coords.latitude, lng: p.coords.longitude } : null;
}
