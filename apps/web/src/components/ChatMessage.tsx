import { MarkdownContent } from "@/lib/markdown";

type Props = {
  role: string;
  content: string;
  streaming?: boolean;
};

export function ChatMessage({ role, content, streaming = false }: Props) {
  const isUser = role === "user";

  if (isUser) {
    return (
      <article className="msg msg-user" aria-label="پیام شما">
        <p className="msg-user-text">{content}</p>
      </article>
    );
  }

  if (streaming) {
    return (
      <article
        className="msg msg-assistant msg-assistant-streaming"
        aria-label="پاسخ در حال دریافت"
        aria-busy="true"
      >
        <p className="msg-stream-text">{content}</p>
      </article>
    );
  }

  return (
    <article className="msg msg-assistant" aria-label="پاسخ عامل">
      <MarkdownContent content={content} />
    </article>
  );
}