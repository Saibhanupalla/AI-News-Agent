// Build-output tests (PHASES phase 7). Run with: npm test
// Requires `npm run build` to have produced dist/ from the committed golden edition.
import { test } from "node:test";
import assert from "node:assert/strict";
import { execSync } from "node:child_process";
import { existsSync, readFileSync, mkdtempSync, readdirSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const WEB_ROOT = fileURLToPath(new URL("..", import.meta.url));
const DIST = path.join(WEB_ROOT, "dist");
const GOLDEN_DATE = "2026-08-24";

function distHtml(...segments) {
  return readFileSync(path.join(DIST, ...segments), "utf-8");
}

test("home page renders Must know stories from the golden edition", () => {
  const html = distHtml("index.html");
  assert.match(html, /Must know/);
  assert.match(html, /OpenAI launches GPT-6 with real-time reasoning/);
  assert.match(html, /EU parliament approves final AI liability rules/);
});

test("stories link out to https sources", () => {
  const html = distHtml("index.html");
  const links = [...html.matchAll(/href="(https:\/\/[^"]+)"[^>]*rel="noopener/g)];
  assert.ok(links.length >= 3, `expected source links, found ${links.length}`);
});

test("continuing stories are labeled as updates", () => {
  const html = distHtml("index.html");
  assert.match(html, /Continuing/);
  assert.match(html, /Update/);
});

test("archive lists the golden edition date", () => {
  const html = distHtml("archive", "index.html");
  assert.match(html, /August 24, 2026/);
  assert.match(html, new RegExp(`/edition/${GOLDEN_DATE}/`));
});

test("edition permalink page was built", () => {
  assert.ok(existsSync(path.join(DIST, "edition", GOLDEN_DATE, "index.html")));
});

test("onboarding dialog and settings button ship with the home page", () => {
  const html = distHtml("index.html");
  assert.match(html, /onboard-dialog/);
  assert.match(html, /What do you want in your briefing\?/);
  assert.match(html, /topic-settings-button/);
  assert.match(html, /Rest of today/);
});

test("build with zero editions shows empty state instead of crashing", () => {
  const emptyDir = mkdtempSync(path.join(tmpdir(), "no-editions-"));
  const outDir = mkdtempSync(path.join(tmpdir(), "empty-dist-"));
  execSync(`npx astro build --outDir ${JSON.stringify(outDir)}`, {
    cwd: WEB_ROOT,
    env: {
      ...process.env,
      EDITIONS_DIR: emptyDir,
      ASTRO_TELEMETRY_DISABLED: "1",
    },
    stdio: "pipe",
  });
  const html = readFileSync(path.join(outDir, "index.html"), "utf-8");
  assert.match(html, /No edition yet/);
  assert.ok(readdirSync(outDir).length > 0);
});
