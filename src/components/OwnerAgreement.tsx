import { useState } from 'react';
import * as DocumentPicker from 'expo-document-picker';
import { api, ok, postFile } from '@/api/client';
import { useQuery } from '@/api/hooks';
import { useStore } from '@/lib/store';
import { Btn, Note, T } from './ui';

/* The owner's own agreement as a PDF. New bookings get a copy with a filled-in cover page; without one, the
   standard Pakka Ghar agreement is used. (Documents come from Files; photos only ever from the camera.) */
export function OwnerAgreement() {
  const { toast } = useStore();
  const q = useQuery(() => ok(api.GET('/api/owner/agreement-template')));
  const [busy, setBusy] = useState(false);
  const upload = async () => {
    const pick = await DocumentPicker.getDocumentAsync({ type: 'application/pdf', copyToCacheDirectory: true });
    if (pick.canceled || !pick.assets?.[0]) return;
    const f = pick.assets[0];
    setBusy(true);
    try {
      const body = await postFile('/api/owner/agreement-template', { uri: f.uri, name: f.name || 'agreement.pdf', type: 'application/pdf', webFile: (f as { file?: Blob }).file }, { name: f.name || 'Agreement' }) as { pages: number };
      toast(`Uploaded: ${body.pages} page${body.pages > 1 ? 's' : ''}. New bookings will use it.`);
      q.reload();
    } catch (e) {
      toast(e instanceof Error ? e.message : 'Upload failed.');
    } finally {
      setBusy(false);
    }
  };
  const t = q.data;
  return (
    <>
      {t ? <Note tone="ok">Using your agreement “{t.name}”, {t.pages} page{t.pages > 1 ? 's' : ''}. Each booking adds a cover page with the resident, room, rent, deposit and dates.</Note>
        : <Note tone="soft">Using the standard Pakka Ghar agreement: term, rent and electricity in the app, deposit in escrow, one month’s notice, police verification and repairs.</Note>}
      <Btn kind="secondary" label={busy ? 'Uploading…' : t ? 'Replace with another PDF' : 'Upload your own agreement (PDF)'} disabled={busy} onPress={upload} />
      {t && <Btn kind="ghost" label="Use the standard agreement instead" disabled={busy} onPress={async () => { await ok(api.POST('/api/owner/agreement-template/remove')); q.reload(); toast('New bookings will use the standard agreement.'); }} />}
      <T v="sm">Residents read every page in the app and sign with their name and a code sent to their phone. You countersign the same way.</T>
    </>
  );
}
