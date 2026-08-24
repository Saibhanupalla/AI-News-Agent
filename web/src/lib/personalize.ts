// Pure personalization logic, kept DOM-free so it can be unit-tested in Node.

export const TOPIC_IDS = [
  "foundation-models",
  "research",
  "startups-funding",
  "policy",
  "open-source",
  "hardware",
  "tools",
  "big-tech",
] as const;

export const STORAGE_KEY = "ai-briefing-topics";

interface StorageLike {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
}

/**
 * null  -> user has never onboarded (show the picker)
 * []    -> user chose "show everything" or skipped
 * [...] -> chosen topic ids (unknown ids silently dropped)
 */
export function loadPrefs(storage: StorageLike): string[] | null {
  const raw = storage.getItem(STORAGE_KEY);
  if (raw === null) return null;
  try {
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(
      (id): id is string => typeof id === "string" && (TOPIC_IDS as readonly string[]).includes(id)
    );
  } catch {
    return [];
  }
}

export function savePrefs(storage: StorageLike, ids: string[]): void {
  const valid = ids.filter((id) => (TOPIC_IDS as readonly string[]).includes(id));
  storage.setItem(STORAGE_KEY, JSON.stringify(valid));
}

/**
 * Split the edition's section topic ids into visible sections and sections that
 * collapse into "Rest of today". Empty prefs mean the full edition is visible.
 * Must know and Continuing are never passed in here - they are always shown.
 */
export function partitionSections(
  sectionTopicIds: string[],
  prefs: string[] | null
): { visible: string[]; collapsed: string[] } {
  if (prefs === null || prefs.length === 0) {
    return { visible: [...sectionTopicIds], collapsed: [] };
  }
  const chosen = new Set(prefs);
  return {
    visible: sectionTopicIds.filter((id) => chosen.has(id)),
    collapsed: sectionTopicIds.filter((id) => !chosen.has(id)),
  };
}
