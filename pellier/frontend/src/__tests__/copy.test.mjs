// Scan src/copy.ts, and the copy in data/*.json, for copy compliance violations.
//
// Rules enforced (Requirement 1.12):
//   1. No emoji (any non-ASCII codepoint except the small allowlist of
//      typographic punctuation we actually use).
//   2. No em dashes (U+2014), and no en dash (U+2013) used as a dash, with a
//      space on either side. An en dash in a range ("10–12") stays allowed.
//   3. No forbidden words (case-insensitive whole-word match) from the
//      storefront conventions: AI, intelligent, smart, agent, LLM, vector,
//      embedding. Plus 'search' used as a standalone noun.
//
// The scanner strips // and /* */ comments and the module-level doc comment
// block before matching forbidden words so documentation explaining the rule
// cannot cause false positives. Emoji and em dash are checked against the
// raw source because typographic glyphs must not appear anywhere in a file
// that ships user-facing copy.
//
// Two narrow exemptions from the word rules, and only from them:
//   - a URL, because a link names its target (the repository name contains
//     "search") rather than speaking to the shopper;
//   - each sentence in ALLOWED_SENTENCES, matched exactly and by name.
//
// `npm test` runs it through src/__tests__/copy_scanner.test.ts. It also runs
// on its own, over copy.ts and data/*.json:
//   node pellier/frontend/src/__tests__/copy.test.mjs
// Exits 0 when clean. Exits 1 with per-violation messages when not.

import { readFile, readdir } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const COPY_PATH = resolve(__dirname, "..", "copy.ts");
// The shopper profiles, guided prompts and catalog in data/ are copy too: the
// storefront shows them. Every JSON file there is scanned except these.
export const DATA_DIR = resolve(__dirname, "..", "..", "..", "..", "data");
export const DATA_NOT_COPY = new Map([
  ["embeddings_cache.json", "the catalog's embedding vectors, numbers only"],
]);

export async function dataCopyFiles() {
  const names = await readdir(DATA_DIR);
  return names.filter((name) => name.endsWith(".json") && !DATA_NOT_COPY.has(name)).sort();
}

// Same allowlist as the Python scanner. Middle dots (U+00B7) are not on it:
// VOICE.md bans them in copy.
const ALLOWED_NON_ASCII = new Set([
  0x00a0, 0x00a9, 0x2013,
  0x2018, 0x2019, 0x201c, 0x201d,
  0x2022, 0x2026, 0x2039, 0x203a,
  0x2318,
]);

const EM_DASH = "\u2014";
const SPACED_EN_DASH = /\s\u2013\s/g;
// A middle dot written as an escape is still a middle dot on screen.
const MIDDLE_DOT_ESCAPE = /\\(?:u00b7|u\{b7\}|xb7)/gi;

const FORBIDDEN_WORDS = [
  "AI",
  "intelligent",
  "smart",
  "agent",
  "LLM",
  "vector",
  "embedding",
];

const SEARCH_SUPPRESS_MARKER = "copy-allow: search-as-verb";

// Exact sentences the word rules may not flag, each with the reason it stays.
// Add one only for a sentence that must say the word to be honest.
export const ALLOWED_SENTENCES = [
  {
    name: "footer imagery disclosure",
    reason: "an honest disclosure that the photographs are generated",
    text: "AI-generated imagery is for illustrative purposes only.",
  },
];

const URL_PATTERN = /https?:\/\/[^\s"'`]+/g;

// Blank a match with spaces so columns in later messages stay accurate.
function blank(text) {
  return " ".repeat(text.length);
}

function exemptFromWordRules(line) {
  let out = line.replace(URL_PATTERN, blank);
  for (const { text } of ALLOWED_SENTENCES) {
    out = out.split(text).join(blank(text));
  }
  return out;
}

// Strip //-line comments, /* */ block comments, and replace them with spaces
// (preserving line and column positions so violation messages stay accurate).
// The module-level comment block at the very top of copy.ts is a run of
// //-prefixed lines and is therefore removed by the line-comment pass.
function stripComments(source) {
  const out = [];
  let i = 0;
  const len = source.length;
  let inSingle = false;
  let inDouble = false;
  let inBacktick = false;
  let inBlock = false;
  let inLineComment = false;

  while (i < len) {
    const ch = source[i];
    const next = i + 1 < len ? source[i + 1] : "";

    if (inLineComment) {
      if (ch === "\n") {
        inLineComment = false;
        out.push("\n");
      } else {
        out.push(" ");
      }
      i += 1;
      continue;
    }
    if (inBlock) {
      if (ch === "*" && next === "/") {
        out.push("  ");
        inBlock = false;
        i += 2;
      } else {
        out.push(ch === "\n" ? "\n" : " ");
        i += 1;
      }
      continue;
    }
    if (inSingle) {
      out.push(ch);
      if (ch === "\\" && i + 1 < len) {
        out.push(source[i + 1]);
        i += 2;
        continue;
      }
      if (ch === "'") inSingle = false;
      i += 1;
      continue;
    }
    if (inDouble) {
      out.push(ch);
      if (ch === "\\" && i + 1 < len) {
        out.push(source[i + 1]);
        i += 2;
        continue;
      }
      if (ch === '"') inDouble = false;
      i += 1;
      continue;
    }
    if (inBacktick) {
      out.push(ch);
      if (ch === "\\" && i + 1 < len) {
        out.push(source[i + 1]);
        i += 2;
        continue;
      }
      if (ch === "`") inBacktick = false;
      i += 1;
      continue;
    }

    if (ch === "/" && next === "/") {
      inLineComment = true;
      out.push("  ");
      i += 2;
      continue;
    }
    if (ch === "/" && next === "*") {
      inBlock = true;
      out.push("  ");
      i += 2;
      continue;
    }
    if (ch === "'") { inSingle = true; out.push(ch); i += 1; continue; }
    if (ch === '"') { inDouble = true; out.push(ch); i += 1; continue; }
    if (ch === "`") { inBacktick = true; out.push(ch); i += 1; continue; }

    out.push(ch);
    i += 1;
  }

  return out.join("");
}

export function scan(source, fileName = "copy.ts") {
  const violations = [];
  const rawLines = source.split("\n");
  const scrubbed = stripComments(source);
  const scrubbedLines = scrubbed.split("\n");

  // 1. Emoji / disallowed non-ASCII.
  for (let lineno = 0; lineno < rawLines.length; lineno++) {
    const line = rawLines[lineno];
    for (let col = 0; col < line.length;) {
      const cp = line.codePointAt(col);
      const width = cp > 0xffff ? 2 : 1;
      if (cp < 128 || ALLOWED_NON_ASCII.has(cp)) {
        col += width;
        continue;
      }
      const cpHex = cp.toString(16).toUpperCase().padStart(4, "0");
      violations.push(
        `${fileName}:${lineno + 1}:${col + 1}: disallowed non-ASCII character U+${cpHex}`,
      );
      col += width;
    }
  }

  // 1b. Middle dots spelled as escapes, which rule 1 cannot see.
  for (let lineno = 0; lineno < rawLines.length; lineno++) {
    MIDDLE_DOT_ESCAPE.lastIndex = 0;
    let m;
    while ((m = MIDDLE_DOT_ESCAPE.exec(rawLines[lineno])) !== null) {
      violations.push(
        `${fileName}:${lineno + 1}:${m.index + 1}: middle dot (${m[0]}) is not allowed; ` +
          "use a comma or a period",
      );
    }
  }

  // 2. Em dash on the raw source.
  for (let lineno = 0; lineno < rawLines.length; lineno++) {
    const line = rawLines[lineno];
    let col = line.indexOf(EM_DASH);
    while (col !== -1) {
      violations.push(
        `${fileName}:${lineno + 1}:${col + 1}: em dash (U+2014) is not allowed in user-facing copy; use a regular hyphen`,
      );
      col = line.indexOf(EM_DASH, col + 1);
    }
    SPACED_EN_DASH.lastIndex = 0;
    let dash;
    while ((dash = SPACED_EN_DASH.exec(line)) !== null) {
      violations.push(
        `${fileName}:${lineno + 1}:${dash.index + 2}: en dash (U+2013) used as a dash; use a period, comma or colon`,
      );
    }
  }

  // 3. Forbidden words, scanned on scrubbed source.
  const wordPatterns = FORBIDDEN_WORDS.map((w) => ({
    word: w,
    pattern: new RegExp(`(?<![A-Za-z0-9_])(${w.replace(/[.*+?^${}()|[\\]\\\\]/g, "\\\\$&")})(?![A-Za-z0-9_])`, "gi"),
  }));
  const searchPattern = /(?<![A-Za-z0-9_])(search)(?![A-Za-z0-9_])/gi;

  for (let lineno = 0; lineno < scrubbedLines.length; lineno++) {
    const line = exemptFromWordRules(scrubbedLines[lineno]);
    const rawLine = rawLines[lineno] ?? "";
    for (const { word, pattern } of wordPatterns) {
      pattern.lastIndex = 0;
      let m;
      while ((m = pattern.exec(line)) !== null) {
        violations.push(
          `${fileName}:${lineno + 1}:${m.index + 1}: forbidden word "${m[0]}" (matches rule: ${word})`,
        );
      }
    }
    if (rawLine.includes(SEARCH_SUPPRESS_MARKER)) continue;
    searchPattern.lastIndex = 0;
    let m;
    while ((m = searchPattern.exec(line)) !== null) {
      violations.push(
        `${fileName}:${lineno + 1}:${m.index + 1}: 'search' used as a standalone noun is forbidden (suppress with '// ${SEARCH_SUPPRESS_MARKER}' on the same line if it is a verb)`,
      );
    }
  }

  return violations;
}

async function main() {
  const violations = scan(await readFile(COPY_PATH, "utf-8"));
  for (const name of await dataCopyFiles()) {
    violations.push(...scan(await readFile(resolve(DATA_DIR, name), "utf-8"), `data/${name}`));
  }
  if (violations.length > 0) {
    console.error("The copy contains compliance violations:");
    for (const v of violations) console.error(`  ${v}`);
    process.exit(1);
  }
  console.log("copy.ts and data/*.json: clean.");
  process.exit(0);
}

// Run only as a script; `copy_scanner.test.ts` imports `scan`.
if (process.argv[1] && resolve(process.argv[1]) === __filename) {
  main().catch((err) => {
    console.error(err);
    process.exit(1);
  });
}
