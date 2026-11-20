import DOMPurify from "dompurify";

/**
 * Sanitise HTML from the `html` tool component before it is inserted into the page.
 * DOMPurify keeps an allowlist of plain HTML tags and attributes (no SVG/MathML, no
 * scripts, event handlers, forms or `javascript:` / `data:` links) and drops the rest.
 */
export function sanitize(html: string): string {
  return DOMPurify.sanitize(html || "", { USE_PROFILES: { html: true }, FORBID_TAGS: ["style", "form"], ADD_ATTR: ["target"] });
}
