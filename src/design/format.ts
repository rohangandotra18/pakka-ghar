/* How dates and times read in the app. Day and month names keep their capitals; only "am"/"pm" are lowercase. */
const ampm = (s: string) => s.replace(/\b(AM|PM)\b/g, x => x.toLowerCase());

/* "Friday 6 pm" */
export const dayHour = (iso: string) => ampm(new Date(iso).toLocaleString('en-IN', { weekday: 'long', hour: 'numeric', hour12: true, timeZone: 'Asia/Kolkata' }));
