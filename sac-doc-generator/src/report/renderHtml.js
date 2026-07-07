import { marked } from "marked";

/** Renders a Markdown report into a self-contained HTML fragment for the browser. */
export function renderReportHtml(markdown) {
  return marked.parse(markdown);
}
