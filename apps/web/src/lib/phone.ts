/** Iranian mobile stored as 989xxxxxxxxx. */
export function normalizeIranMobile(input: string): string | null {
  let digits = input.replace(/\D/g, "");
  if (digits.startsWith("0098")) digits = digits.slice(4);
  else if (digits.startsWith("98")) digits = digits.slice(2);
  else if (digits.startsWith("0")) digits = digits.slice(1);
  if (!/^9\d{9}$/.test(digits)) return null;
  return `98${digits}`;
}

export function formatIranMobile(stored: string | null | undefined): string {
  if (!stored) return "";
  if (stored.startsWith("98") && stored.length === 12) return `0${stored.slice(2)}`;
  return stored;
}
