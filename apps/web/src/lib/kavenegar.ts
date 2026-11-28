import { formatIranMobile } from "@/lib/phone";

const LOOKUP_PATH = "verify/lookup.json";

export type KavenegarLookupResult =
  | { ok: true; messageId?: number }
  | { ok: false; message: string; status?: number };

type KavenegarReturn = {
  return?: { status?: number; message?: string };
  entries?: Array<{ messageid?: number }>;
};

/** Panel template name; Liara may use KAVENEGAR_TEMPLATE_NAME or TEMPLATE_NAME. */
export function kavenegarTemplateName(): string | null {
  const name =
    process.env.KAVENEGAR_TEMPLATE_NAME?.trim() ||
    process.env.TEMPLATE_NAME?.trim() ||
    process.env.TEMPELATE_NAME?.trim();
  return name || null;
}

export function isKavenegarConfigured(): boolean {
  return Boolean(process.env.KAVENEGAR_API_KEY?.trim() && kavenegarTemplateName());
}

function lookupUserMessage(status: number | undefined, providerMessage: string | undefined): string {
  switch (status) {
    case 418:
      return "سرویس پیامک موقتاً در دسترس نیست";
    case 424:
      return "پیکربندی پیامک نادرست است";
    case 426:
    case 428:
    case 431:
    case 432:
      return "ارسال کد تأیید ممکن نیست";
    case 422:
      return "شماره یا کد برای ارسال پیامک مناسب نیست";
    case 403:
    case 401:
      return "سرویس پیامک پیکربندی نشده است";
    default:
      if (providerMessage && /شماره|موبایل|receptor/i.test(providerMessage)) {
        return "شماره موبایل نامعتبر است";
      }
      return "ارسال پیامک ناموفق بود";
  }
}

/**
 * Kavenegar verify/lookup — template must include %token (see kavenegar.com REST Lookup).
 * Token for OTP: digits only (required for SMS; voice call path needs numeric token).
 */
export async function sendKavenegarLookup(
  receptorStored: string,
  token: string,
): Promise<KavenegarLookupResult> {
  const apiKey = process.env.KAVENEGAR_API_KEY?.trim();
  const template = kavenegarTemplateName();
  if (!apiKey || !template) {
    return { ok: false, message: "پیکربندی پیامک کامل نیست" };
  }
  if (!/^\d{4,8}$/.test(token)) {
    return { ok: false, message: "کد نامعتبر" };
  }

  const receptor = formatIranMobile(receptorStored);
  if (!receptor) return { ok: false, message: "شماره نامعتبر" };

  const params = new URLSearchParams({
    receptor,
    token,
    template,
    type: "sms",
  });
  const tag = process.env.KAVENEGAR_TAG?.trim();
  if (tag && /^[a-zA-Z0-9_-]+$/.test(tag) && tag.length <= 200) {
    params.set("tag", tag);
  }

  const url = `https://api.kavenegar.com/v1/${encodeURIComponent(apiKey)}/${LOOKUP_PATH}`;

  try {
    const res = await fetch(url, {
      method: "POST",
      body: params,
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      cache: "no-store",
    });
    const body = (await res.json().catch(() => null)) as KavenegarReturn | null;
    const status = body?.return?.status;
    if (status === 200) {
      const messageId = body?.entries?.[0]?.messageid;
      return { ok: true, messageId };
    }
    const message = lookupUserMessage(status, body?.return?.message?.trim());
    return { ok: false, message, status };
  } catch {
    return { ok: false, message: "ارسال پیامک ناموفق بود" };
  }
}