import { formatIranMobile } from "@/lib/phone";

export function userDisplayLabel(user: {
  display_name?: string | null;
  phone?: string | null;
}): string {
  const name = user.display_name?.trim();
  if (name) return name;
  return formatIranMobile(user.phone) || "—";
}

export function userContactLine(user: { phone?: string | null }): string {
  return formatIranMobile(user.phone) || "";
}