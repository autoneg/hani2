import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

export function Markdown({ text, size, className = "" }: { text: string; size?: "sm" | "md" | "lg"; className?: string }) {
  return (
    <div className={`md ${size === "sm" ? "md-sm" : size === "lg" ? "md-lg" : ""} ${className}`}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{ a: ({ node, ...p }) => <a {...p} target="_blank" rel="noreferrer" /> }}
      >
        {text || ""}
      </ReactMarkdown>
    </div>
  );
}
