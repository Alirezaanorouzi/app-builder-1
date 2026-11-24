import { fa } from "@/lib/dict";

type Props = {
  visible: boolean;
};

export function ThinkingLoader({ visible }: Props) {
  if (!visible) return null;
  return (
    <div role="status" aria-live="polite" aria-busy="true" className="thinking-loader">
      <span className="thinking-loader-mark" aria-hidden />
      <span className="thinking-loader-text">{fa.thinking}</span>
    </div>
  );
}