import type {CatalogSkill} from './skillCatalog';

// Ranked skill search. Rules (carry/site-redesign-20261107/design.md section 3):
// 1. when some skill has every query word, only those are shown, so "upgrade
//    check" narrows instead of widening; else every skill with any query word
//    is shown, best score first (FILLER verbs not counted), so a word no skill
//    knows lowers the match instead of emptying it; when no word matches at
//    all, every skill is listed, as for a stop-word-only query;
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
// assessment" (eks-cost-intelligence SKILL.md:12, :18), whose name says cost;
// "too expensive" is the same ask.
const ALIAS = new Map(
  [['k8s', 'kubernetes'], ['save', 'cost'], ['money', 'cost'], ['spend', 'cost'], ['expensive', 'cost']].map(
    ([from, to]) => [stem(from), stem(to)],
  ),
);
// Phrases visitors type that a skill's own text lacks, indexed with its summary.
// Each is true of its skill, by the SKILL.md description line quoted beside it.
const PHRASES: Record<string, string[]> = {
  // skills/eks-build/SKILL.md:3 "Use when building EKS clusters. Generates complete,
  // production-ready Terraform projects"; "generating EKS Terraform code from scratch".
  'eks-build': ['deploy an EKS cluster', 'set up a new Kubernetes cluster on EKS', 'spin up EKS'],
  // skills/ecs-build/SKILL.md:3 "apply-ready code for clusters, services, and task definitions".
  'ecs-build': ['deploy an ECS cluster'],
  // skills/eks-cost-intelligence/SKILL.md:3 "how much am I wasting on EKS?",
  // "dollar-quantified findings and ready-to-apply remediation snippets".
  'eks-cost-intelligence': ['make my cluster cheaper', 'cut my EKS bill'],
};
// Verbs that start many tasks ("set up ingress", "spin up fargate"). They still
// match, so "spin up eks" finds its phrase and "up" alone finds its skills, but
// they do not rank a partial match: "up" is a part-word hit in "upgrade".
const FILLER = new Set(['set', 'up', 'spin', 'make', 'new', 'cut'].map(stem));
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
    summary: new Set([
      ...words(positive([skill.use, skill.summary].filter(Boolean).join('. '), names)),
      ...words((PHRASES[skill.name] ?? []).join(' ')),
    ]),
    description: new Set(words(positive(skill.description, names))),
  }));
}

// "devops agent" is read as one word, so "devops" alone is not an agent word.
const AGENT_WORD = stem('agent');
const DEVOPS_AGENT = `${stem('devops')} ${AGENT_WORD}`;
const AGENT = new Set([AGENT_WORD, DEVOPS_AGENT]);

// passing: some word was found only in the long description; matched: how many
// query words the skill has.
function score(entry: Indexed, query: string[]): {score: number; passing: boolean; matched: number} {
  const name = ` ${entry.name} `;
  let total = 0;
  let passing = false;
  let matched = 0;
  for (const word of query) {
    if (name.includes(` ${word} `)) total += 10;
    else if (entry.agent && AGENT.has(word)) total += entry.agent;
    else if (entry.name.includes(word)) total += 6;
    else if (entry.summary.has(word)) total += 3;
    else if (entry.description.has(word)) {
      total += 1;
      passing = true;
    } else continue;
    matched += 1;
  }
  if (name.includes(` ${query.join(' ')} `)) total += 20;
  return {score: total, passing, matched};
}

// port: an agent query found a skill that has an AWS DevOps Agent page;
// partial: the skill does not have every query word.
export type Hit = {skill: CatalogSkill; score: number; passing: boolean; port: boolean; partial: boolean};

export function search(index: Indexed[], query: string): Hit[] {
  const q = queryWords(query);
  // Only stop words, such as "aws skills": the whole catalogue, EKS first.
  if (q.length === 0 && words(query).length === 0) return [];
  const agentQuery = q.some((w) => AGENT.has(w));
  const telling = q.filter((w) => !FILLER.has(w));
  const scored = index.map((entry) => ({
    skill: entry.skill,
    port: agentQuery && entry.port,
    ...(q.length === 0 ? {score: 0, passing: false, matched: 0} : score(entry, q)),
    told: telling.length > 0 ? score(entry, telling).score : 0,
  }));
  // Rule 1: when some skill has every query word, keep only those; else keep
  // every skill with at least one, best score first; none matched keeps all.
  const most = Math.max(...scored.map((hit) => hit.matched));
  const least = most === q.length ? most : Math.min(most, 1);
  // A partial match ranks by its words other than FILLER, when it has any.
  const rank = (hit: (typeof scored)[number]) => (most < q.length && telling.length > 0 ? hit.told : hit.score);
  return scored
    .filter((hit) => hit.matched >= least)
    .sort(
      (a, b) =>
        rank(b) - rank(a) ||
        b.score - a.score ||
        PLATFORM_ORDER[a.skill.group] - PLATFORM_ORDER[b.skill.group] ||
        a.skill.name.localeCompare(b.skill.name),
    )
    .map(({matched, told, ...hit}) => ({...hit, partial: matched < q.length}));
}
