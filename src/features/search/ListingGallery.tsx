import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react';
import { Image, Modal, Pressable, ScrollView, View, useWindowDimensions, type HostInstance } from 'react-native';
import { C, F, R, T, useWide } from '@/design';
import type { Schemas } from '@/core/api';
import { mediaUrl } from '@/core/device';

type Photo = Schemas['ListingPhotoOut'];

const day = (iso: string) => new Date(iso).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' });
/* "Room 101 · Taken on site, 11 Nov" */
const captionOf = (ph: Photo) => `${ph.room ? `Room ${ph.room} · ` : ''}Taken on site, ${day(ph.taken_at)}`;
const altOf = (ph: Photo, pgName: string) => ph.caption || (ph.room ? `Photo of room ${ph.room}` : `Photo of ${pgName}`);

/* The line under the photos. */
export function ListingPhotoNote() {
  return <T v="sm">Every photo was taken at the building with the Pakka Ghar camera. No stock, edited or AI pictures.</T>;
}

/* On a phone: a strip to swipe through. */
function PhotoStrip({ photos, pgName }: { photos: Photo[]; pgName: string }) {
  return (
    <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 8 }}>
      {photos.map(ph => (
        <View key={ph.id} style={{ width: 260, gap: 4 }}>
          <Image source={{ uri: mediaUrl(ph.url) }} style={{ width: 260, height: 180, borderRadius: R.md, backgroundColor: C.surface2 }} accessibilityLabel={ph.caption || `Photo${ph.room ? ` of room ${ph.room}` : ''}`} />
          <T v="sm" style={{ fontSize: 11 }}>{captionOf(ph)}</T>
        </View>
      ))}
    </ScrollView>
  );
}

type Corners = { tl?: boolean; tr?: boolean; bl?: boolean; br?: boolean };
const radii = (c: Corners) => ({ borderTopLeftRadius: c.tl ? R.lg : 0, borderTopRightRadius: c.tr ? R.lg : 0, borderBottomLeftRadius: c.bl ? R.lg : 0, borderBottomRightRadius: c.br ? R.lg : 0 });

/* One picture of the mosaic. Pressing it opens the viewer. */
function Tile({ photo, pgName, corners, flex, more, tileRef, onPress }: {
  photo: Photo; pgName: string; corners: Corners; flex?: number; more?: number; tileRef: (el: HostInstance | null) => void; onPress: () => void;
}) {
  return (
    <Pressable ref={tileRef} accessibilityRole="button" accessibilityLabel={`Open photo: ${altOf(photo, pgName)}`} onPress={onPress}
      style={({ pressed }) => [{ flex, overflow: 'hidden', backgroundColor: C.surface2, opacity: pressed ? 0.9 : 1 }, radii(corners)]}>
      <Image source={{ uri: mediaUrl(photo.url) }} resizeMode="cover" style={{ width: '100%', height: '100%' }} accessibilityLabel={altOf(photo, pgName)} />
      {more ? <View pointerEvents="none" style={{ position: 'absolute', right: 12, bottom: 12, backgroundColor: C.ink, borderRadius: R.pill, paddingHorizontal: 10, paddingVertical: 5 }}><T v="smBold" style={{ color: C.bg }}>+{more} more</T></View> : null}
    </Pressable>
  );
}

function Mosaic({ photos, pgName, onOpen, tileRef }: { photos: Photo[]; pgName: string; onOpen: (i: number) => void; tileRef: (i: number) => (el: HostInstance | null) => void }) {
  const n = photos.length;
  const [a, b, c] = photos;
  if (n === 1) return <View style={{ height: 420 }}><Tile photo={a} pgName={pgName} corners={{ tl: true, tr: true, bl: true, br: true }} flex={1} tileRef={tileRef(0)} onPress={() => onOpen(0)} /></View>;
  if (n === 2) return (
    <View style={{ height: 380, flexDirection: 'row', gap: 8 }}>
      <Tile photo={a} pgName={pgName} corners={{ tl: true, bl: true }} flex={1} tileRef={tileRef(0)} onPress={() => onOpen(0)} />
      <Tile photo={b} pgName={pgName} corners={{ tr: true, br: true }} flex={1} tileRef={tileRef(1)} onPress={() => onOpen(1)} />
    </View>
  );
  return (
    <View style={{ height: 420, flexDirection: 'row', gap: 8 }}>
      <Tile photo={a} pgName={pgName} corners={{ tl: true, bl: true }} flex={2} tileRef={tileRef(0)} onPress={() => onOpen(0)} />
      <View style={{ flex: 1, gap: 8 }}>
        <Tile photo={b} pgName={pgName} corners={{ tr: true }} flex={1} tileRef={tileRef(1)} onPress={() => onOpen(1)} />
        <Tile photo={c} pgName={pgName} corners={{ br: true }} flex={1} more={n > 3 ? n - 3 : undefined} tileRef={tileRef(2)} onPress={() => onOpen(2)} />
      </View>
    </View>
  );
}

/* Round dark button used in the viewer. */
function RoundBtn({ label, glyph, onPress, disabled, btnRef }: { label: string; glyph: string; onPress: () => void; disabled?: boolean; btnRef?: (el: HostInstance | null) => void }) {
  return (
    <Pressable ref={btnRef} accessibilityRole="button" accessibilityLabel={label} accessibilityState={{ disabled: !!disabled }} disabled={disabled} onPress={onPress}
      style={({ pressed }) => ({ width: 48, height: 48, borderRadius: 24, alignItems: 'center', justifyContent: 'center', backgroundColor: pressed ? '#3A423E' : '#262C29', opacity: disabled ? 0.3 : 1 })}>
      <T v="h2" style={{ color: '#FFFFFF', fontFamily: F.regular, fontSize: 30, lineHeight: 34 }}>{glyph}</T>
    </Pressable>
  );
}

/* The full-window viewer. React Native's Modal on the website draws into the page body above everything (the site
   header too), is a dialog with aria-modal, keeps Tab inside it, closes on Escape and puts focus back where it was.
   We add the arrow keys and move focus to the close button on open. */
function Viewer({ photos, pgName, index, setIndex, onClose }: { photos: Photo[]; pgName: string; index: number; setIndex: (i: number) => void; onClose: () => void }) {
  const { width, height } = useWindowDimensions();
  const closeRef = useRef<HostInstance | null>(null);
  const n = photos.length;
  const photo = photos[index];
  const step = useCallback((d: number) => setIndex(Math.min(n - 1, Math.max(0, index + d))), [index, n, setIndex]);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'ArrowLeft') { e.preventDefault(); step(-1); }
      else if (e.key === 'ArrowRight') { e.preventDefault(); step(1); }
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [step]);
  useEffect(() => { const t = setTimeout(() => closeRef.current?.focus(), 30); return () => clearTimeout(t); }, []);
  return (
    <Modal transparent animationType="none" visible onRequestClose={onClose} accessibilityLabel={`Photos of ${pgName}`}>
      <View style={{ flex: 1, backgroundColor: 'rgba(8,10,9,0.97)', paddingVertical: 24, paddingHorizontal: 24 }}>
        <View style={{ flexDirection: 'row', justifyContent: 'flex-end' }}>
          <RoundBtn label="Close photos" glyph="×" onPress={onClose} btnRef={el => { closeRef.current = el; }} />
        </View>
        <View style={{ flex: 1, flexDirection: 'row', alignItems: 'center', gap: 16 }}>
          <RoundBtn label="Previous photo" glyph="‹" onPress={() => step(-1)} disabled={index === 0} />
          <View style={{ flex: 1, height: '100%', minHeight: Math.min(200, height - 220), maxWidth: width - 200 }}>
            <Image source={{ uri: mediaUrl(photo.url) }} resizeMode="contain" style={{ width: '100%', height: '100%' }} accessibilityLabel={altOf(photo, pgName)} />
          </View>
          <RoundBtn label="Next photo" glyph="›" onPress={() => step(1)} disabled={index === n - 1} />
        </View>
        <View style={{ alignItems: 'center', gap: 4, paddingTop: 12 }}>
          <T v="body" style={{ color: '#FFFFFF' }}>{captionOf(photo)}</T>
          <T v="sm" style={{ color: '#B8C2BC' }} >{index + 1} of {n}</T>
        </View>
      </View>
    </Modal>
  );
}

/* The photos of a PG. Phones get a strip; a wide website gets a mosaic and a viewer. With no photos the caller's
   `fallback` (the map) is shown. */
export function ListingGallery({ photos, pgName, fallback }: { photos: Photo[]; pgName: string; fallback: ReactNode }) {
  const wide = useWide();
  const [open, setOpen] = useState<number | null>(null);
  const tiles = useRef<(HostInstance | null)[]>([]);
  const tileRef = (i: number) => (el: HostInstance | null) => { tiles.current[i] = el; };
  const from = useRef(0);
  const show = (i: number) => { from.current = i; setOpen(i); };
  const close = () => {
    setOpen(null);
    /* put focus back on the tile that opened the viewer (some browsers do not focus a pressed button themselves) */
    setTimeout(() => tiles.current[from.current]?.focus(), 60);
  };
  if (photos.length === 0) return <>{fallback}</>;
  if (!wide) return <PhotoStrip photos={photos} pgName={pgName} />;
  return (
    <>
      <Mosaic photos={photos} pgName={pgName} onOpen={show} tileRef={tileRef} />
      {open != null && <Viewer photos={photos} pgName={pgName} index={open} setIndex={setOpen} onClose={close} />}
    </>
  );
}
