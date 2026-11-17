// 檢查 CLAUDE.md 第 7 節：除了 design-tokens.css，CSS 不可以出現色碼或寫死的 px
// （@media 斷點例外，CSS 變數不能用在 @media 裡）
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

// fileURLToPath 才會把中文路徑解碼回來（.pathname 會留著 %E5…）
const root = fileURLToPath(new URL("../src", import.meta.url));
const problems = [];
const walk = (dir) => {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) walk(p);
    else if (p.endsWith(".css") && !p.endsWith("design-tokens.css")) check(p);
  }
};
const check = (file) => {
  readFileSync(file, "utf8").split(/\r?\n/).forEach((line, i) => {
    const code = line.replace(/\/\*.*?\*\//g, "");
    if (/#[0-9a-fA-F]{3,8}\b/.test(code)) problems.push(`${file}:${i + 1} 色碼請改用 var(--color-…)`);
    if (/\d+px/.test(code) && !/@media/.test(code)) problems.push(`${file}:${i + 1} px 請改用 tokens`);
  });
};
walk(root);
if (problems.length) {
  console.error(problems.join("\n"));
  process.exit(1);
}
console.log("styles ok");
