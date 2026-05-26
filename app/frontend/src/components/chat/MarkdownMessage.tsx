"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

interface Props {
  content: string;
  inverted?: boolean;
}

export function MarkdownMessage({ content, inverted }: Props) {
  return (
    <div
      className={`chat-markdown text-sm leading-relaxed ${inverted ? "chat-markdown-inverted" : ""}`}
    >
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={{
        a: ({ href, children }) => (
          <a
            href={href}
            target="_blank"
            rel="noopener noreferrer"
            className={inverted ? "underline text-white/90" : "text-safar-navy underline"}
          >
            {children}
          </a>
        ),
        p: ({ children }) => <p className="mb-2 last:mb-0">{children}</p>,
        ul: ({ children }) => <ul className="mb-2 list-disc pl-5 space-y-1">{children}</ul>,
        ol: ({ children }) => <ol className="mb-2 list-decimal pl-5 space-y-1">{children}</ol>,
        li: ({ children }) => <li>{children}</li>,
        strong: ({ children }) => <strong className="font-semibold">{children}</strong>,
        h1: ({ children }) => <h3 className="font-semibold text-base mb-2 mt-1">{children}</h3>,
        h2: ({ children }) => <h3 className="font-semibold text-sm mb-2 mt-1">{children}</h3>,
        h3: ({ children }) => <p className="font-semibold mb-1">{children}</p>,
        code: ({ children }) => (
          <code
            className={`rounded px-1 py-0.5 text-xs font-mono ${
              inverted ? "bg-white/15" : "bg-gray-100 text-gray-800"
            }`}
          >
            {children}
          </code>
        ),
        pre: ({ children }) => (
          <pre
            className={`mb-2 overflow-x-auto rounded-lg p-3 text-xs ${
              inverted ? "bg-white/10" : "bg-gray-100"
            }`}
          >
            {children}
          </pre>
        ),
      }}
    >
      {content}
    </ReactMarkdown>
    </div>
  );
}
