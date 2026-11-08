import type {CatalogSkill} from './skillCatalog';

// Ranked skill search. Rules (carry/site-redesign-20261107/design.md section 3):
// 1. every query word must match (AND), so "upgrade check" narrows instead of
//    widening;
// 2. words are whole words, compared after a trailing "s", then "ing", then
//    "e" is cut, so "upgrades" finds "upgrade" and "settings" finds
//    "setting" (a doubled last letter left by "ing" is undoubled, so "running"
//    finds "run"); words under 2 characters, and the STOP words of a task
//    sentence ("how do i ... my"), are dropped, and an ALIAS word is read as
//    its target, and the phrase "devops agent" is one agent word. A version
//    number matches only as a skill's text writes it:
//    "1.32" finds eks-upgrade-check, "1.34" and "v1.32" find nothing;
// 3. per word, a whole-word hit in the skill name scores 10, a part-word hit
//    in the name 6 (as does "agent" for a PORTS skill, 7 for apex), the short
//    summary 3, the description 1; the whole query found as whole words in
//    the name adds 20, which makes that skill the top hit;
// 4. description sentences are cut at a phrase that routes away from the
//    skill ("not for", "skip for", "do not use", ...), and a ";" clause that
//    names a skill in the manifest, or says "use <skill-name>", is not indexed;
// 5. ties break by the manifest group (EKS, ECS, general), then by name; the
//    group, not the catalogue's platform, so dotnet-aws-ecs (manifest general,
//    ECS filter) still follows ecs-architect for "fargate". A query of stop
//    words only ("aws skills") lists every skill in that order.

const ROUTE_AWAY = /\b(do not use|not for|skip for|route elsewhere|use instead)\b/i;
const SKILL_TOKEN = /\b[a-z0-9]+(-[a-z0-9]+)+\b/g;
// "for cost/TCO use ecs-cost-intelligence" (ecs-operation-review) routes to a
// skill that does not ship yet.
const ROUTE_TO = /\buse [a-z0-9]+(-[a-z0-9]+)+\b/;
// Query words only. "skills" stems to "skill"; the rest are the filler of a
// task sentence such as "how do i upgrade my cluster".
const STOP = new Set(
  ['skill', 'aws', 'amazon', 'how', 'do', 'does', 'can', 'should', 'me', 'my', 'our', 'we', 'you', 'your', 'the', 'an', 'to',
    'for', 'from', 'of', 'in', 'on', 'with', 'what', 'which', 'is', 'are', 'it', 'this', 'help', 'want', 'need', 'please'].map(stem),
);
// A word visitors type for one the skills use. Each target is the word in the
// skill's own text: "Native K8s" next to Kubernetes (eks-best-practices
// SKILL.md:35); "wasting money, and how much can I save" and "spending
// assessment" (eks-cost-intelligence SKILL.md:12, :18), whose name says cost.
const ALIAS = new Map(
  [['k8s', 'kubernetes'], ['save', 'cost'], ['money', 'cost'], ['spend', 'cost']].map(
    ([from, to]) => [stem(from), stem(to)],
  ),
);
// "agent" finds the skills that also run in AWS DevOps Agent (PORTS, the
// folders under devops-agent/) and apex, the router, first, so the home
// search keeps it in view, all ahead of eks-mcp-server, whose use line only
// says "connect your agent".
const PORTS = new Set(['eks-cost-intelligence', 'eks-ingress-migration', 'eks-operation-review', 'eks-recon',
  'eks-security', 'eks-upgrade-check']);
const ROUTER = 'apex';
const PLATFORM_ORDER = {eks: 0, ecs: 1, general: 2} as const;

type Indexed = {skill: CatalogSkill; name: string; port: boolean; agent: number; summary: Set<string>; description: Set<string>};

function positive(text: string, names: Set<string>): string {
  return text
    .split(/(?<=[.!?])\s+/)
    .map((sentence) => {
      const cut = sentence.search(ROUTE_AWAY);
      const kept = cut === -1 ? sentence : sentence.slice(0, cut);
      return kept
        .split(';')
        .filter((clause) => !ROUTE_TO.test(clause) && !(clause.match(SKILL_TOKEN) ?? []).some((token) => names.has(token)))
        .join(';');
    })
    .join(' ');
}

function stem(word: string): string {
  let w = word;
  for (const end of ['s', 'ing', 'e']) {
    if (end === 's' && w.endsWith('ss')) continue;
    if (w.endsWith(end) && w.length - end.length >= 3) {
      w = w.slice(0, -end.length);
      if (end === 'ing' && w.length >= 4 && /([^aeioulsz])\1$/.test(w)) w = w.slice(0, -1);
    }
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
  const out: string[] = [];
  for (const w of kept) {
    if (w === AGENT_WORD && out[out.length - 1] === stem('devops')) out[out.length - 1] = DEVOPS_AGENT;
    else out.push(w);
  }
  return [...new Set(out)];
}

export function buildIndex(skills: CatalogSkill[]): Indexed[] {
  const names = new Set(skills.map((s) => s.name));
  return skills.map((skill) => ({
    skill,
    name: words(skill.name.replace(/-/g, ' ')).join(' '),
    port: PORTS.has(skill.name),
    agent: PORTS.has(skill.name) ? 6 : skill.name === ROUTER ? 7 : 0,
    // The hand-written "use" line, as on the page (skillCatalog.ts SKILLS), and the manifest summary.
    summary: new Set(words(positive([skill.use, skill.summary].filter(Boolean).join('. '), names))),
    description: new Set(words(positive(skill.description, names))),
  }));
}

// "devops agent" is read as one word, so "devops" alone is not an agent word.
const AGENT_WORD = stem('agent');
const DEVOPS_AGENT = `${stem('devops')} ${AGENT_WORD}`;
const AGENT = new Set([AGENT_WORD, DEVOPS_AGENT]);

// passing: some word was found only in the long description.
function score(entry: Indexed, query: string[]): {score: number; passing: boolean} {
  const name = ` ${entry.name} `;
  let total = 0;
  let passing = false;
  for (const word of query) {
    if (name.includes(` ${word} `)) total += 10;
    else if (entry.agent && AGENT.has(word)) total += entry.agent;
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

// port: an agent query found a skill that has an AWS DevOps Agent page.
export type Hit = {skill: CatalogSkill; score: number; passing: boolean; port: boolean};

export function search(index: Indexed[], query: string): Hit[] {
  const q = queryWords(query);
  // Only stop words, such as "aws skills": the whole catalogue, EKS first.
  if (q.length === 0 && words(query).length === 0) return [];
  const agentQuery = q.some((w) => AGENT.has(w));
  return index
    .map((entry) => ({
      skill: entry.skill,
      port: agentQuery && entry.port,
      ...(q.length === 0 ? {score: 0, passing: false} : score(entry, q)),
    }))
    .filter((hit) => q.length === 0 || hit.score > 0)
    .sort(
      (a, b) =>
        b.score - a.score ||
        PLATFORM_ORDER[a.skill.group] - PLATFORM_ORDER[b.skill.group] ||
        a.skill.name.localeCompare(b.skill.name),
    );
}
