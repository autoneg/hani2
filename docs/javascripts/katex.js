// Render the math that pymdownx.arithmatex (generic mode) marked. Only the
// .arithmatex elements are rendered, so other dollar signs stay plain text.
document$.subscribe(() => {
  document.querySelectorAll(".arithmatex").forEach((el) => {
    renderMathInElement(el, {
      delimiters: [
        { left: "\\(", right: "\\)", display: false },
        { left: "\\[", right: "\\]", display: true },
      ],
      throwOnError: false,
    });
  });
});
