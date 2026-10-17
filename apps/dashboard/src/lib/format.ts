// Display helpers for API values. Times are UTC, like the API.
const months = [
  "Jan",
  "Feb",
  "Mar",
  "Apr",
  "May",
  "Jun",
  "Jul",
  "Aug",
  "Sep",
  "Oct",
  "Nov",
  "Dec",
];
const two = (n: number) => String(n).padStart(2, "0");

export const number = (n: number) => n.toLocaleString("en-US");
export const percent = (n: number, digits = 1) => `${n.toFixed(digits)}%`;
/** "14:05" */
export function timeUTC(iso: string) {
  const d = new Date(iso);
  return `${two(d.getUTCHours())}:${two(d.getUTCMinutes())}`;
}
/** "Oct 16" */
export function dateUTC(iso: string) {
  const d = new Date(iso);
  return `${months[d.getUTCMonth()]} ${d.getUTCDate()}`;
}
/** "Oct 16, 14:05" */
export const dateTimeUTC = (iso: string) => `${dateUTC(iso)}, ${timeUTC(iso)}`;
/** "Oct 16, 13:05 – Oct 17, 13:05" (the date is left out of the end when it is the same day). */
export function windowCaption(start: string, end: string) {
  const same = dateUTC(start) === dateUTC(end);
  return `${dateTimeUTC(start)}–${same ? timeUTC(end) : dateTimeUTC(end)}`;
}
export const capitalize = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);
/** "1.5 KB"; null when the size is unknown. */
export const formatBytes = (n: number | null) =>
  n === null
    ? null
    : n < 1024
      ? `${n} B`
      : n < 1024 * 1024
        ? `${(n / 1024).toFixed(1)} KB`
        : `${(n / 1024 / 1024).toFixed(1)} MB`;
