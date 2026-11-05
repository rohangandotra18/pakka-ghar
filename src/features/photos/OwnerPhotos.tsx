import { useState } from 'react';
import { Image, View } from 'react-native';
import { api, ApiError, ok, useQuery } from '@/core/api';
import { mediaUrl, takeOnSitePhoto, uploadShot } from '@/core/device';
import { useStore } from '@/core/session';
import { C, R, Btn, Chip, Chips, T } from '@/design';

/* The owner's listing photos. Each is taken now, with the camera, standing at the building; there's no way to
   pick a picture from the gallery, and the server refuses anything taken elsewhere or earlier. */
export function OwnerPhotos({ rooms }: { rooms: string[] }) {
  const { toast, refresh } = useStore();
  const q = useQuery(() => ok(api.GET('/api/owner/photos')));
  const [room, setRoom] = useState('');
  const [busy, setBusy] = useState(false);
  const take = async () => {
    setBusy(true);
    try {
      const shot = await takeOnSitePhoto();
      if (!shot) return;
      await uploadShot('/api/owner/photos', shot, room ? { room } : {});
      toast('Photo added. It shows on your listing marked “taken on site”.');
      q.reload();
      refresh();
    } catch (e) {
      toast(e instanceof ApiError ? e.message : 'The photo could not be added.');
    } finally {
      setBusy(false);
    }
  };
  const photos = q.data ?? [];
  return (
    <View style={{ gap: 10 }}>
      {photos.length > 0 && (
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6 }}>
          {photos.map(p => (
            <View key={p.id} style={{ width: '31%', gap: 2 }}>
              <Image source={{ uri: mediaUrl(p.thumb) }} style={{ width: '100%', aspectRatio: 1, borderRadius: R.sm, backgroundColor: C.surface2 }} accessibilityLabel={p.room ? `Photo of room ${p.room}` : 'Photo of the PG'} />
              <T v="sm" style={{ fontSize: 10 }}>{p.room ? `Room ${p.room}` : 'Common area'} · {p.distance_m} m</T>
            </View>
          ))}
        </View>
      )}
      <T v="label">This photo shows</T>
      <Chips>
        <Chip label="Building or common area" on={!room} onPress={() => setRoom('')} />
        {rooms.map(r => <Chip key={r} label={`Room ${r}`} on={room === r} onPress={() => setRoom(r)} />)}
      </Chips>
      <Btn kind="secondary" label={busy ? 'Opening camera…' : 'Take a photo'} disabled={busy} onPress={take} />
      <T v="sm">Take them at the PG: the app checks your phone’s location against your pin and the time. Gallery, edited and AI pictures aren’t accepted, so tenants can trust what they see.</T>
    </View>
  );
}
