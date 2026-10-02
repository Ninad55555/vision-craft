// monaco-editor 0.57 types live behind the package `exports` map; these shims
// type the deep ESM paths via the public `monaco-editor` types. Vite resolves
// the same specifiers at runtime; only html/css/javascript are ever imported.
declare module 'monaco-editor/editor/editor.api.js' {
  import * as monaco from 'monaco-editor'
  export = monaco
}
declare module 'monaco-editor/languages/definitions/css/register.js'
declare module 'monaco-editor/languages/definitions/html/register.js'
declare module 'monaco-editor/languages/definitions/javascript/register.js'
declare module 'monaco-editor/language/css/monaco.contribution.js'
declare module 'monaco-editor/language/html/monaco.contribution.js'
declare module 'monaco-editor/language/typescript/monaco.contribution.js'
declare module 'monaco-editor/editor/editor.worker.js?worker' {
  const w: new () => Worker
  export default w
}
declare module 'monaco-editor/language/html/html.worker.js?worker' {
  const w: new () => Worker
  export default w
}
declare module 'monaco-editor/language/css/css.worker.js?worker' {
  const w: new () => Worker
  export default w
}
declare module 'monaco-editor/language/typescript/ts.worker.js?worker' {
  const w: new () => Worker
  export default w
}
