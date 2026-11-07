import type {CatalogSkill} from './skillCatalog';

// Ranked skill search. Rules (carry/site-redesign-20261107/design.md section 3):
// 1. every query word must match (AND), so "upgrade check" narrows instead of
//    widening;
// 2. per word, a whole-word hit in the skill name scores 10, a part-word hit
//    in the name 6, the short summary 3, the description 1; the whole query
//    found in the name adds 20, which makes that skill the top hit;
// 3. description sentences that route away from the skill ("not for",
//    "skip for", "do not use", ...) are not indexed: they name other skills;
// 4. ties break by name.

const ROUTE_AWAY = /\b(do not use|not for|skip for|route elsewhere|use instead)\b/i;

type Indexed = {skill: CatalogSkill; name: string; summary: string; description: string};

function positive(text: string): string {
  return text
    .split(/(?<=[.;])\s+/)
    .filter((sentence) => !ROUTE_AWAY.test(sentence))
    .join(' ')
    .toLowerCase();
}

function escape(word: string): string {
  return word.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

export function queryWords(query: string): string[] {
  return query
    .toLowerCase()
    .split(/[^a-z0-9.+#]+/)
    .filter(Boolean);
}

export function buildIndex(skills: CatalogSkill[]): Indexed[] {
  return skills.map((skill) => ({
    skill,
    name: skill.name.toLowerCase().replace(/-/g, ' '),
    // Until the manifest carries a summary, the catalogue's "use" line stands in.
    summary: positive(skill.summary ?? skill.use ?? ''),
    description: positive(skill.description),
  }));
}

// passing: some word was found only in the long description.
function score(entry: Indexed, words: string[]): {score: number; passing: boolean} {
  let total = 0;
  let passing = false;
  for (const word of words) {
    if (new RegExp(`\\b${escape(word)}\\b`).test(entry.name)) total += 10;
    else if (entry.name.includes(word)) total += 6;
    else if (entry.summary.includes(word)) total += 3;
    else if (entry.description.includes(word)) {
      total += 1;
      passing = true;
    } else return {score: 0, passing};
  }
  if (entry.name.includes(words.join(' '))) total += 20;
  return {score: total, passing};
}

export type Hit = {skill: CatalogSkill; score: number; passing: boolean};

export function search(index: Indexed[], query: string): Hit[] {
  const words = queryWords(query);
  if (words.length === 0) return [];
  return index
    .map((entry) => ({skill: entry.skill, ...score(entry, words)}))
    .filter((hit) => hit.score > 0)
    .sort((a, b) => b.score - a.score || a.skill.name.localeCompare(b.skill.name));
}
