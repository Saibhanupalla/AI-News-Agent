// Unit tests for the pure personalization logic (PHASES phase 8).
// Node strips the TypeScript types on import, so no build step is needed.
import { test } from "node:test";
import assert from "node:assert/strict";

import {
  STORAGE_KEY,
  loadPrefs,
  partitionSections,
  savePrefs,
} from "../src/lib/personalize.ts";

function fakeStorage(initial = {}) {
  const store = new Map(Object.entries(initial));
  return {
    getItem: (key) => (store.has(key) ? store.get(key) : null),
    setItem: (key, value) => store.set(key, String(value)),
  };
}

test("never-onboarded user returns null (picker should open)", () => {
  assert.equal(loadPrefs(fakeStorage()), null);
});

test("prefs filter sections; unchosen topics collapse", () => {
  const sections = ["foundation-models", "research", "policy", "tools"];
  const { visible, collapsed } = partitionSections(sections, ["research"]);
  assert.deepEqual(visible, ["research"]);
  assert.deepEqual(collapsed, ["foundation-models", "policy", "tools"]);
});

test("empty prefs show the full edition", () => {
  const sections = ["foundation-models", "research"];
  assert.deepEqual(partitionSections(sections, []), {
    visible: ["foundation-models", "research"],
    collapsed: [],
  });
  assert.deepEqual(partitionSections(sections, null), {
    visible: ["foundation-models", "research"],
    collapsed: [],
  });
});

test("unknown pref ids are ignored, not crashing", () => {
  const storage = fakeStorage({
    [STORAGE_KEY]: JSON.stringify(["research", "not-a-topic", 42]),
  });
  assert.deepEqual(loadPrefs(storage), ["research"]);
});

test("corrupt storage value degrades to empty prefs", () => {
  const storage = fakeStorage({ [STORAGE_KEY]: "{not json" });
  assert.deepEqual(loadPrefs(storage), []);
});

test("save/load round trip persists across 'reloads'", () => {
  const storage = fakeStorage();
  savePrefs(storage, ["policy", "hardware", "bogus-id"]);
  // A "reload" is just a fresh loadPrefs call against the same storage.
  assert.deepEqual(loadPrefs(storage), ["policy", "hardware"]);
});

test("skip saves an explicit empty list so the picker never reopens", () => {
  const storage = fakeStorage();
  savePrefs(storage, []);
  assert.deepEqual(loadPrefs(storage), []);
  assert.notEqual(loadPrefs(storage), null);
});
