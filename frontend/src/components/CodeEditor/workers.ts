// Minimal Monaco workers for VisionCraft: HTML + CSS + JS(+TS impl) + base editor.
// Deliberately EXCLUDED: json/python/java/c/markdown/sql/yaml and all other workers.
// Uses Vite `?worker` handling per https://github.com/microsoft/monaco-editor/blob/main/docs/integrate-esm.md
// Paths go through the package `exports` map so Vite 8/Rolldown can resolve them.
import CssWorker from 'monaco-editor/language/css/css.worker.js?worker'
import EditorWorker from 'monaco-editor/editor/editor.worker.js?worker'
import HtmlWorker from 'monaco-editor/language/html/html.worker.js?worker'
import TsWorker from 'monaco-editor/language/typescript/ts.worker.js?worker'

export function installMonacoWorkers(): void {
  const g = self as unknown as { MonacoEnvironment: unknown }
  g.MonacoEnvironment = {
    getWorker: (_: unknown, label: string) => {
      if (label === 'html' || label === 'handlebars' || label === 'razor') return new HtmlWorker()
      if (label === 'css' || label === 'scss' || label === 'less') return new CssWorker()
      if (label === 'typescript' || label === 'javascript') return new TsWorker()
      return new EditorWorker()
    },
  }
}
