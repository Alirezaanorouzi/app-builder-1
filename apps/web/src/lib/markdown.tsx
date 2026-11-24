import type { ReactNode } from "react";

/** Lightweight markdown for assistant replies (lists, headings, emphasis). */

function inlineFormat(text: string): ReactNode[] {
  const parts: ReactNode[] = [];
  const re = /(\*\*[^*]+\*\*|`[^`]+`)/g;
  let last = 0;
  let m: RegExpExecArray | null;
  let key = 0;
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) {
      parts.push(text.slice(last, m.index));
    }
    const token = m[0];
    if (token.startsWith("**")) {
      parts.push(
        <strong key={key++}>{token.slice(2, -2)}</strong>
      );
    } else if (token.startsWith("`")) {
      parts.push(
        <code key={key++} className="md-inline-code">
          {token.slice(1, -1)}
        </code>
      );
    }
    last = m.index + token.length;
  }
  if (last < text.length) {
    parts.push(text.slice(last));
  }
  return parts.length ? parts : [text];
}

export function MarkdownContent({ content }: { content: string }) {
  const lines = content.replace(/\r\n/g, "\n").split("\n");
  const blocks: ReactNode[] = [];
  let ul: string[] = [];
  let ol: string[] = [];
  let key = 0;

  const flushUl = () => {
    if (!ul.length) return;
    blocks.push(
      <ul key={key++} className="md-list">
        {ul.map((item, i) => (
          <li key={i}>{inlineFormat(item)}</li>
        ))}
      </ul>
    );
    ul = [];
  };

  const flushOl = () => {
    if (!ol.length) return;
    blocks.push(
      <ol key={key++} className="md-list md-list-ol">
        {ol.map((item, i) => (
          <li key={i}>{inlineFormat(item)}</li>
        ))}
      </ol>
    );
    ol = [];
  };

  const flushLists = () => {
    flushUl();
    flushOl();
  };

  for (const raw of lines) {
    const line = raw.trimEnd();
    const bullet = line.match(/^\s*[-*•]\s+(.+)$/);
    const numbered = line.match(/^\s*\d+[.)]\s+(.+)$/);

    if (bullet) {
      flushOl();
      ul.push(bullet[1]);
      continue;
    }
    if (numbered) {
      flushUl();
      ol.push(numbered[1]);
      continue;
    }

    flushLists();

    if (!line.trim()) {
      blocks.push(<div key={key++} className="md-spacer" aria-hidden />);
      continue;
    }
    if (line.startsWith("### ")) {
      blocks.push(
        <h3 key={key++} className="md-h3">
          {inlineFormat(line.slice(4))}
        </h3>
      );
      continue;
    }
    if (line.startsWith("## ")) {
      blocks.push(
        <h2 key={key++} className="md-h2">
          {inlineFormat(line.slice(3))}
        </h2>
      );
      continue;
    }
    if (line.startsWith("# ")) {
      blocks.push(
        <h1 key={key++} className="md-h1">
          {inlineFormat(line.slice(2))}
        </h1>
      );
      continue;
    }
    blocks.push(
      <p key={key++} className="md-p">
        {inlineFormat(line)}
      </p>
    );
  }

  flushLists();
  return <div className="md-root">{blocks}</div>;
}