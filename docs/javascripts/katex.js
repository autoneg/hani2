// Render the maths of pages written with pymdownx.arithmatex (generic mode) using KaTeX.
// Arithmatex wraps maths in \( \) and \[ \]; plain dollar signs elsewhere are left alone.
document$.subscribe(({ body }) => {
  renderMathInElement(body, {
    delimiters: [
      { left: "\\(", right: "\\)", display: false },
      { left: "\\[", right: "\\]", display: true },
    ],
    throwOnError: false,
  });
});
