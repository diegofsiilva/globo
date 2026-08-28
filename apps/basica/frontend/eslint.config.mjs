/** Configuração de análise estática do frontend Next.js. */
import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";
import jsdoc from "eslint-plugin-jsdoc";

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  // Override default ignores of eslint-config-next.
  globalIgnores([
    // Default ignores of eslint-config-next:
    ".next/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
  ]),

  // JSDoc obrigatório no que é exportado.
  //
  // O AGENTS.md exige "JSDoc em JavaScript/TypeScript" desde o início, mas a
  // regra dependia de revisão humana — e 110 exports passaram sem documentação.
  // Esta configuração transforma a convenção em algo que `npm run lint` verifica.
  //
  // Só `require-jsdoc` está ligado, e não o conjunto de validação de tags: o
  // TypeScript já garante os tipos, então `@param {string}` seria ruído
  // duplicado. O que falta num código tipado é o PORQUÊ, e isso nenhuma regra
  // consegue verificar — ela só garante que haja onde escrevê-lo.
  {
    files: ["src/**/*.ts", "src/**/*.tsx"],
    plugins: { jsdoc },
    rules: {
      "jsdoc/require-jsdoc": [
        "error",
        {
          publicOnly: true,
          require: {
            FunctionDeclaration: true,
            ArrowFunctionExpression: true,
            FunctionExpression: true,
            ClassDeclaration: true,
            MethodDefinition: true,
          },
          contexts: [
            "ExportNamedDeclaration > TSTypeAliasDeclaration",
            "ExportNamedDeclaration > TSInterfaceDeclaration",
            "ExportNamedDeclaration > VariableDeclaration",
          ],
          enableFixer: false,
        },
      ],
    },
  },

  // Fixtures e cenários de mock ficam de fora.
  //
  // São dados de exemplo, não API de produção: exigir um bloco de documentação
  // acima de cada constante de cenário produziria dezenas de linhas que repetem
  // o nome da variável — ruído que ensina a ignorar o próprio aviso.
  {
    files: ["src/**/_mocks/**/*.ts", "src/**/_mocks/**/*.tsx"],
    rules: { "jsdoc/require-jsdoc": "off" },
  },

  // O mesmo vale para os testes: o cenário está no NOME do caso.
  {
    files: ["tests/**/*.ts", "tests/**/*.tsx"],
    rules: { "jsdoc/require-jsdoc": "off" },
  },

  // As primitivas shadcn/ui também ficam de fora.
  //
  // São wrappers finos sobre Radix, gerados pelo CLI do shadcn e mantidos como
  // conjunto fechado (ver AGENTS.md, regra 7). Documentar cada reexport
  // (`SheetTitle`, `TableCell`, `TooltipTrigger`) repetiria o nome do
  // componente, e o texto útil já está na documentação do Radix. O que é NOSSO
  // — a composição dessas primitivas nas telas — continua exigindo JSDoc.
  {
    files: ["src/components/ui/**/*.tsx"],
    rules: { "jsdoc/require-jsdoc": "off" },
  },
]);

export default eslintConfig;
