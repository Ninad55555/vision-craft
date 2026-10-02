// ESM-only Monaco setup via the package `exports` map (`./*.js` -> `./esm/vs/*.js`).
// Only the editor API + html/css/javascript are ever imported — no json, python,
// java, markdown, sql, yaml, or any other language. (In 0.57 the Monarch
// grammars live under `languages/definitions/<lang>/register.js`; importing
// `basic-languages/monaco.contribution` would pull ALL of them, so we don't.)
import * as monaco from 'monaco-editor/editor/editor.api.js'
import 'monaco-editor/languages/definitions/css/register.js'
import 'monaco-editor/languages/definitions/html/register.js'
import 'monaco-editor/languages/definitions/javascript/register.js'
import 'monaco-editor/language/css/monaco.contribution.js'
import 'monaco-editor/language/html/monaco.contribution.js'
import 'monaco-editor/language/typescript/monaco.contribution.js'

export { monaco }
