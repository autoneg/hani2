// Run with `npm test`. The `html` tool component's sanitiser, fed classic XSS payloads.
import assert from "node:assert/strict";
import { test } from "node:test";
import { JSDOM } from "jsdom";

// DOMPurify binds to `window` when first loaded, so set it up before importing.
const { window } = new JSDOM("");
Object.assign(globalThis, { window, DOMParser: window.DOMParser });
const { sanitize } = await import("../src/ui/sanitize.ts");

const PAYLOADS = [
  `<script>alert(1)</script>`,
  `<ScRiPt>alert(1)</sCrIpT>`,
  `<img src=x onerror=alert(1)>`,
  `<IMG SRC=x OnErRoR="alert(1)">`,
  `<svg onload=alert(1)>`,
  `<svg><script>alert(1)</script></svg>`,
  `<body onload=alert(1)>`,
  `<iframe src="javascript:alert(1)"></iframe>`,
  `<iframe srcdoc="<script>alert(1)</script>"></iframe>`,
  `<a href="javascript:alert(1)">x</a>`,
  `<a href="JaVaScRiPt:alert(1)">x</a>`,
  `<a href="java&#9;script:alert(1)">x</a>`,
  `<a href="&#106;avascript:alert(1)">x</a>`,
  `<a href="data:text/html,<script>alert(1)</script>">x</a>`,
  `<svg><a xlink:href="javascript:alert(1)"><text>x</text></a></svg>`,
  `<svg><a><animate attributeName="href" values="javascript:alert(1)"/><text>x</text></a></svg>`,
  `<form action="javascript:alert(1)"><button>x</button></form>`,
  `<form><button formaction="javascript:alert(1)">x</button></form>`,
  `<math><mtext><table><mglyph><style><img src=x onerror=alert(1)>`,
  `<object data="javascript:alert(1)"></object>`,
  `<embed src="javascript:alert(1)">`,
  `<meta http-equiv="refresh" content="0;url=javascript:alert(1)">`,
  `<base href="javascript:alert(1)//">`,
  `<details open ontoggle=alert(1)>`,
  `<input autofocus onfocus=alert(1)>`,
  `<style>@import "javascript:alert(1)";</style>`,
  `<link rel=stylesheet href="javascript:alert(1)">`,
];

const DANGEROUS_TAGS = new Set(["script", "iframe", "object", "embed", "style", "link", "meta", "base", "form", "animate", "set"]);

function problems(html: string): string[] {
  const out: string[] = [];
  const body = new window.DOMParser().parseFromString(html, "text/html").body;
  for (const el of Array.from(body.querySelectorAll("*")) as Element[]) {
    const tag = el.localName.toLowerCase();
    if (DANGEROUS_TAGS.has(tag)) out.push(`<${tag}>`);
    for (const a of Array.from(el.attributes)) {
      const v = a.value.replace(/[\s\u0000-\u001f]/g, "").toLowerCase();
      if (a.name.toLowerCase().startsWith("on")) out.push(`${tag}[${a.name}]`);
      if (/^(javascript|vbscript|data):/.test(v) && !(tag === "img" && v.startsWith("data:image/"))) out.push(`${tag}[${a.name}=${a.value}]`);
      if (a.name === "srcdoc" || a.name === "formaction" || a.name === "action") out.push(`${tag}[${a.name}]`);
    }
  }
  return out;
}

for (const p of PAYLOADS) {
  test(`neutralises ${p}`, () => {
    assert.deepEqual(problems(sanitize(p)), [], sanitize(p));
  });
}

test("keeps ordinary formatting, tables, links and images", () => {
  const html = sanitize(
    `<p><b>bold</b> <i>it</i> <a href="https://example.org/x">link</a></p>` +
      `<table><tr><th>a</th></tr><tr><td>1</td></tr></table><img src="data:image/png;base64,AAAA" alt="pic">`,
  );
  const body = new window.DOMParser().parseFromString(html, "text/html").body;
  assert.equal(body.querySelector("b")?.textContent, "bold");
  assert.equal(body.querySelector("a")?.getAttribute("href"), "https://example.org/x");
  assert.equal(body.querySelector("td")?.textContent, "1");
  assert.equal(body.querySelector("img")?.getAttribute("src"), "data:image/png;base64,AAAA");
});
