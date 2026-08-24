import { readdirSync, readFileSync, existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

export interface EditionSource {
  name: string;
  url: string;
}

export interface EditionItem {
  cluster_id: string;
  title: string;
  summary: string;
  why_it_matters: string;
  topic_ids: string[];
  story_type: "news" | "update" | "opinion" | "evergreen";
  update_delta: string;
  sources: EditionSource[];
}

export interface Edition {
  date: string;
  intro: string;
  must_know: EditionItem[];
  sections: Record<string, EditionItem[]>;
  continuing: EditionItem[];
}

export const TOPIC_LABELS: Record<string, string> = {
  "foundation-models": "Foundation models",
  research: "Research",
  "startups-funding": "Startups and funding",
  policy: "Policy and regulation",
  "open-source": "Open source",
  hardware: "Hardware / chips",
  tools: "Tools and products",
  "big-tech": "Big Tech",
};

// EDITIONS_DIR env override exists so tests can build against an empty directory.
const EDITIONS_DIR =
  process.env.EDITIONS_DIR ??
  fileURLToPath(new URL("../../../data/editions", import.meta.url));

export function listEditionDates(): string[] {
  if (!existsSync(EDITIONS_DIR)) return [];
  return readdirSync(EDITIONS_DIR)
    .filter((name) => name.endsWith(".json"))
    .map((name) => name.replace(".json", ""))
    .sort()
    .reverse();
}

export function loadEdition(date: string): Edition {
  const raw = readFileSync(path.join(EDITIONS_DIR, `${date}.json`), "utf-8");
  return JSON.parse(raw) as Edition;
}

export function latestEdition(): Edition | null {
  const [latest] = listEditionDates();
  return latest ? loadEdition(latest) : null;
}

export function formatDate(date: string): string {
  return new Date(`${date}T00:00:00Z`).toLocaleDateString("en-US", {
    weekday: "long",
    year: "numeric",
    month: "long",
    day: "numeric",
    timeZone: "UTC",
  });
}
