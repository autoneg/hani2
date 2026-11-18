import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Tex } from "./math";
import { placeholderTex, protectMath } from "./mathText";

/**
 * Markdown (GitHub flavour). With `math`, `$...$` and `$$...$$` are rendered
 * with KaTeX (see `mathText.ts` for the rule that keeps "$5" as text; `\$` is
 * a literal dollar). Math is opt-in: chat and scenario texts stay plain.
 */
export function Markdown({ text, size, className = "", math = false }: { text: string; size?: "sm" | "md" | "lg"; className?: string; math?: boolean }) {
  return (
    <div className={`md ${size === "sm" ? "md-sm" : size === "lg" ? "md-lg" : ""} ${className}`}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: ({ node, ...p }) => <a {...p} target="_blank" rel="noreferrer" />,
          ...(math
            ? {
                code: ({ node, children, ...p }) => {
                  const m = typeof children === "string" ? placeholderTex(children) : null;
                  return m ? <Tex tex={m.tex} display={m.display} /> : <code {...p}>{children}</code>;
                },
              }
            : {}),
        }}
      >
        {math ? protectMath(text || "") : text || ""}
      </ReactMarkdown>
    </div>
  );
}
