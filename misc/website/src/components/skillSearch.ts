import type {CatalogSkill} from './skillCatalog';

// Ranked skill search. Rules (carry/site-redesign-20261107/design.md section 3):
// 1. every query word must match (AND), so "upgrade check" narrows instead of
//    widening;
// 2. words are whole words, compared after a trailing "ing", "s" or "es"
//    (then "e") is cut, so "upgrades" finds "upgrade"; words under 2
//    characters, and the STOP words of a task sentence ("how do i ... my"),
//    are dropped, and an ALIAS word is read as its target;
// 3. per word, a whole-word hit in the skill name scores 10, a part-word hit
//    in the name 6, the short summary 3, the description 1; the whole query
//    found as whole words in the name adds 20, which makes that skill the top
//    hit;
// 4. description sentences are cut at a phrase that routes away from the
//    skill ("not for", "skip for", "do not use", ...), and a ";" clause that
//    names a skill (eks-... or ecs-...) is not indexed;
// 5. ties break by platform (EKS, ECS, general), then by name.

const ROUTE_AWAY = /\b(do not use|not for|skip for|route elsewhere|use instead)\b/i;
const SKILL_TOKEN = /\b(eks|ecs)-[a-z]+(-[a-z]+)*\b/i;
// Query words only. "skills" stems to "skill"; the rest are the filler of a
// task sentence such as "how do i upgrade my cluster".
const STOP = new Set(
  ['skill', 'how', 'do', 'does', 'can', 'should', 'me', 'my', 'our', 'we', 'you', 'your', 'the', 'an', 'to', 'for',
    'of', 'in', 'with', 'what', 'which', 'is', 'are', 'it', 'this', 'help', 'want', 'need', 'please'].map(stem),
);
// A word visitors type for one the skills use. Each target is the word in the
// skill's own text: "Native K8s" next to Kubernetes (eks-best-practices
// SKILL.md:35); "wasting money, and how much can I save" and "spending
// assessment" (eks-cost-intelligence SKILL.md:12, :18), whose name says cost.
const ALIAS = new Map(
  [['k8s', 'kubernetes'], ['save', 'cost'], ['saving', 'cost'], ['money', 'cost'], ['spend', 'cost'], ['spending', 'cost']].map(
    ([from, to]) => [stem(from), stem(to)],
  ),
);
const PLATFORM_ORDER = {eks: 0, ecs: 1, general: 2} as const;

type Indexed = {skill: CatalogSkill; name: string; summary: Set<string>; description: Set<string>};

function positive(text: string): string {
  return text
    .split(/(?<=[.!?])\s+/)
    .map((sentence) => {
      const cut = sentence.search(ROUTE_AWAY);
      const kept = cut === -1 ? sentence : sentence.slice(0, cut);
      return kept
        .split(';')
        .filter((clause) => !SKILL_TOKEN.test(clause))
        .join(';');
    })
    .join(' ');
}

function stem(word: string): string {
  let w = word;
  for (const end of ['ing', 's', 'e']) {
    if (end === 's' && w.endsWith('ss')) continue;
    if (w.endsWith(end) && w.length - end.length >= 3) w = w.slice(0, -end.length);
  }
  return w;
}

// Words as the index and the query both see them: "." stays inside a word,
// so "1.32" is one word, and [.+#] are trimmed from its ends.
function words(text: string): string[] {
  return text
    .toLowerCase()
    .split(/[^a-z0-9.+#]+/)
    .map((w) => w.replace(/^[.+#]+|[.+#]+$/g, ''))
    .filter((w) => w.length >= 2)
    .map(stem);
}

export function queryWords(query: string): string[] {
  const kept = words(query)
    .filter((w) => !STOP.has(w))
    .map((w) => ALIAS.get(w) ?? w);
  return [...new Set(kept)];
}

export function buildIndex(skills: CatalogSkill[]): Indexed[] {
  return skills.map((skill) => ({
    skill,
    name: words(skill.name.replace(/-/g, ' ')).join(' '),
    // Until the manifest carries a summary, the catalogue's "use" line stands in.
    summary: new Set(words(positive(skill.summary ?? skill.use ?? ''))),
    description: new Set(words(positive(skill.description))),
  }));
}

// passing: some word was found only in the long description.
function score(entry: Indexed, query: string[]): {score: number; passing: boolean} {
  const name = ` ${entry.name} `;
  let total = 0;
  let passing = false;
  for (const word of query) {
    if (name.includes(` ${word} `)) total += 10;
    else if (entry.name.includes(word)) total += 6;
    else if (entry.summary.has(word)) total += 3;
    else if (entry.description.has(word)) {
      total += 1;
      passing = true;
    } else return {score: 0, passing};
  }
  if (name.includes(` ${query.join(' ')} `)) total += 20;
  return {score: total, passing};
}

export type Hit = {skill: CatalogSkill; score: number; passing: boolean};

export function search(index: Indexed[], query: string): Hit[] {
  const q = queryWords(query);
  if (q.length === 0) return [];
  return index
    .map((entry) => ({skill: entry.skill, ...score(entry, q)}))
    .filter((hit) => hit.score > 0)
    .sort(
      (a, b) =>
        b.score - a.score ||
        PLATFORM_ORDER[a.skill.group] - PLATFORM_ORDER[b.skill.group] ||
        a.skill.name.localeCompare(b.skill.name),
    );
}
