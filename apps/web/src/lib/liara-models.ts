/** Liara catalog model IDs — must match LIARA_MODELS / NEXT_PUBLIC_DEFAULT_MODEL in .env */

const LITELLM_VENDOR_PREFIXES = ["deepseek/", "anthropic/", "google/", "meta/", "mistral/"];

export function liaraWireModelId(
  requested: string | null | undefined,
  defaultModel: string,
): string {
  let m = (requested ?? defaultModel).trim() || defaultModel.trim();
  while (m.startsWith("openai/openai/")) {
    m = m.slice("openai/".length);
  }
  if (m.startsWith("openai/")) {
    const rest = m.slice("openai/".length);
    if (LITELLM_VENDOR_PREFIXES.some((v) => rest.startsWith(v))) {
      return rest;
    }
  }
  return m;
}

export function pickLiaraModel(
  requested: string | null | undefined,
  defaultModel: string,
  allowed: string[],
): string {
  const wire = liaraWireModelId(requested, defaultModel);
  if (!allowed.length) return wire;
  if (allowed.includes(wire)) return wire;
  if (allowed.includes(defaultModel)) return defaultModel;
  return allowed[0]!;
}

export function listLiaraModelsFromEnv(): string[] {
  const fromList = process.env.LIARA_MODELS?.split(",")
    .map((s) => s.trim())
    .filter(Boolean);
  if (fromList?.length) return fromList;
  const one = process.env.NEXT_PUBLIC_DEFAULT_MODEL?.trim();
  return one ? [one] : ["deepseek/deepseek-v4.1-flash-1017"];
}