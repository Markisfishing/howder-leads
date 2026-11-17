import js from "@eslint/js";
import reactHooks from "eslint-plugin-react-hooks";
import globals from "globals";
import tseslint from "typescript-eslint";

export default tseslint.config(
  { ignores: ["dist", "prototypes", "node_modules"] },
  {
    extends: [js.configs.recommended, ...tseslint.configs.recommended],
    files: ["**/*.{ts,tsx}"],
    languageOptions: { globals: globals.browser },
    plugins: { "react-hooks": reactHooks },
    rules: {
      ...reactHooks.configs.recommended.rules,
      // 頁面不直接呼叫 fetch，一律經過 src/api/（CLAUDE.md 第 4 節第 1 點）
      "no-restricted-globals": ["error", { name: "fetch", message: "請改用 src/api/ 裡的函式" }],
      // 底線開頭的參數代表「刻意不用」（例如 mock 的簽名要對上）
      "@typescript-eslint/no-unused-vars": ["error", { argsIgnorePattern: "^_" }],
    },
  },
  {
    files: ["src/api/client.ts"],
    rules: { "no-restricted-globals": "off" },
  },
);
