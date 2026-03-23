"use client";

import { motion } from "framer-motion";
import { Bot } from "lucide-react";
import Markdown from "react-markdown";

interface AIRecommendationsProps {
  text: string;
}

export default function AIRecommendations({ text }: AIRecommendationsProps) {
  if (!text) return null;

  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      className="glass-panel rounded-2xl p-6"
    >
      <div className="flex items-center gap-2 mb-4">
        <div
          className="flex h-6 w-6 items-center justify-center rounded-lg"
          style={{ background: "var(--accent-muted)" }}
        >
          <Bot size={14} style={{ color: "var(--accent)" }} />
        </div>
        <h3 className="font-display text-sm tracking-widest" style={{ color: "var(--text-primary)" }}>
          AI РЕКОМЕНДАЦИИ
        </h3>
      </div>

      <div
        className="prose prose-sm max-w-none"
        style={{ color: "var(--text-secondary)" }}
      >
        <Markdown
          skipHtml
          allowedElements={["h1", "h2", "h3", "p", "ul", "ol", "li", "strong", "em", "a", "br", "code", "pre", "blockquote"]}
          components={{
            h1: ({ children }) => (
              <h3 className="font-display text-base font-semibold mt-4 mb-2" style={{ color: "var(--text-primary)" }}>
                {children}
              </h3>
            ),
            h2: ({ children }) => (
              <h4 className="font-display text-sm font-semibold mt-3 mb-1.5" style={{ color: "var(--text-primary)" }}>
                {children}
              </h4>
            ),
            h3: ({ children }) => (
              <h5 className="text-sm font-semibold mt-2 mb-1" style={{ color: "var(--text-primary)" }}>
                {children}
              </h5>
            ),
            p: ({ children }) => (
              <p className="text-sm leading-relaxed mb-2" style={{ color: "var(--text-secondary)" }}>
                {children}
              </p>
            ),
            ul: ({ children }) => (
              <ul className="list-disc pl-4 space-y-1 mb-2">{children}</ul>
            ),
            ol: ({ children }) => (
              <ol className="list-decimal pl-4 space-y-1 mb-2">{children}</ol>
            ),
            li: ({ children }) => (
              <li className="text-sm" style={{ color: "var(--text-secondary)" }}>{children}</li>
            ),
            strong: ({ children }) => (
              <strong style={{ color: "var(--text-primary)" }}>{children}</strong>
            ),
            em: ({ children }) => (
              <em style={{ color: "var(--accent)" }}>{children}</em>
            ),
            blockquote: ({ children }) => (
              <blockquote
                className="pl-3 my-2 text-sm italic"
                style={{ borderLeft: "2px solid var(--accent)", color: "var(--text-muted)" }}
              >
                {children}
              </blockquote>
            ),
            code: ({ children }) => (
              <code
                className="rounded px-1.5 py-0.5 font-mono text-xs"
                style={{ background: "var(--input-bg)", color: "var(--accent)" }}
              >
                {children}
              </code>
            ),
          }}
        >
          {text}
        </Markdown>
      </div>
    </motion.div>
  );
}
