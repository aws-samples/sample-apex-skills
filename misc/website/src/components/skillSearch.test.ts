// Ranking table test for the skill finder, over the real manifest.
// Run from the repo root: node --experimental-strip-types --test misc/website/src/components/skillSearch.test.ts
// --experimental-strip-types needs Node 22.6 or later (package.json engines says >=20). No npm
// script runs this test; CI runs it in .github/workflows/docs-sync.yml.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync, readdirSync} from 'node:fs';

const here = new URL('.', import.meta.url);
const {buildIndex, queryWords, search} = await import(new URL('skillSearch.ts', here).href);
const manifest = JSON.parse(readFileSync(new URL('../../static/manifests/skills.json', here), 'utf8'));
// The hand-written use lines stand in for the summary, as in skillCatalog.ts.
const catalog = readFileSync(new URL('skillCatalog.ts', here), 'utf8');
const uses = Object.fromEntries(
  [...catalog.matchAll(/'?([a-z-]+)'?: \{\s*job: '[a-z]+',\s*use: '([^']+)'/g)].map((m) => [m[1], m[2]]),
);
const index = buildIndex(manifest.map((s: {name: string}) => ({...s, use: uses[s.name]})));

type Hit = {skill: {name: string}; score: number; passing: boolean; port: boolean};

// What the finder shows (SkillFinder.tsx): the best match, the strong rows,
// and the row Enter opens.
function shown(query: string) {
  const hits: Hit[] = search(index, query);
  const top = hits[0] && hits[0].score >= 20 && (!hits[1] || hits[0].score > hits[1].score) ? hits[0] : null;
  const strong = hits.filter((h) => !h.passing);
  const main = (strong.length > 0 ? strong : hits).filter((h) => h !== top);
  const first = top ?? main[0] ?? hits[0];
  return {
    total: hits.length,
    first: first?.skill.name,
    rows: [top, ...main].filter(Boolean).map((h) => (h as Hit).skill.name),
    all: hits.map((h) => h.skill.name),
  };
}

test('every use line is read', () => {
  assert.equal(Object.keys(uses).length, manifest.length);
});

// [query, first row (Enter), and optionally the most results allowed]
const FIRST: [string, string, number?][] = [
  // The design queries (design.md section 3).
  ['upgrade check', 'eks-upgrade-check', 2],
  ['upgrade', 'eks-upgrade-check'],
  ['cost', 'eks-cost-intelligence'],
  ['ingress', 'eks-ingress-migration'],
  ['terraform', 'terraform-skill'],
  ['security', 'eks-security'],
  ['well architected', 'eks-well-architected-review'],
  ['recon', 'eks-recon'],
  ['ecs security', 'ecs-security'],
  ['operation review', 'eks-operation-review'],
  ['mcp', 'eks-mcp-server'],
  ['graviton', 'graviton-migration'],
  // M1: route-away text does not send an EKS user to an ECS page.
  ['kubernetes', 'eks-best-practices'],
  ['kubernetes upgrade', 'eks-upgrade-check'],
  // M2: the word is in the skill's own use line.
  ['fargate', 'ecs-architect'],
  ['harden', 'eks-security'],
  ['llm', 'eks-genai'],
  ['write a skill', 'skill-creator'],
  // 392-1: the skill the apex router names (skills/apex/SKILL.md:19, :57, :61, :74).
  ['ecs on fargate', 'ecs-architect'],
  ['run containers on ecs', 'ecs-architect'],
  ['cis benchmark', 'eks-security'],
  ['compliance', 'eks-security'],
  ['karpenter', 'eks-best-practices'],
  // 392-1 (X-1): the manifest summary is indexed with the use line ("canary" is in ecs-devops's summary).
  ['canary', 'ecs-devops'],
  // Router :76, "stuck deployment": ecs-devops.
  ['deployment', 'ecs-devops'],
  // M5 and S2: plurals, -ing, the word "skill", a trailing period, "1.32".
  ['secure', 'eks-security'],
  ['upgrades', 'eks-upgrade-check'],
  ['upgrading', 'eks-upgrade-check'],
  ['costs', 'eks-cost-intelligence'],
  ['upgrade check.', 'eks-upgrade-check', 2],
  ['1.32', 'eks-upgrade-check'],
  ['terraform skill', 'terraform-skill'],
  // D1: task sentences drop their filler words; a few aliases.
  ['how do i upgrade my cluster', 'eks-upgrade-check'],
  ['audit my cluster', 'eks-operation-review'],
  ['what is running in my cluster', 'eks-recon'],
  ['help me write a skill', 'skill-creator'],
  ['save money', 'eks-cost-intelligence'],
  ['k8s', 'eks-best-practices'],
  ['k8s upgrade', 'eks-upgrade-check'],
  // Site search feedback: most words, not all, plus each skill's phrases.
  // eks-build is "Use when building EKS clusters" (skills/eks-build/SKILL.md:3).
  ['i want to deploy an eks cluster', 'eks-build'],
  ['deploy eks cluster', 'eks-build'],
  // First only by tie order: eks-build and ecs-build both score 6, and EKS sorts first.
  ['deploy a cluster', 'eks-build'],
  // First only by tie order with eks-ingress-migration, eks-security and eks-upgrade-check (6 each).
  ['set up a new kubernetes cluster', 'eks-build'],
  ['i want to build an eks cluster', 'eks-build'],
  // eks-cost-intelligence: "how much am I wasting on EKS?" (skills/eks-cost-intelligence/SKILL.md:3).
  ['make my cluster cheaper', 'eks-cost-intelligence'],
  ['my cluster is too expensive', 'eks-cost-intelligence'],
];

for (const [query, want, most] of FIRST) {
  test(`"${query}" shows ${want} first`, () => {
    const r = shown(query);
    assert.equal(r.first, want, `rows: ${r.rows.join(', ')}`);
    if (most !== undefined) assert.ok(r.total <= most, `${r.total} results`);
  });
}

test('M1: a skill that only routes away is not matched', () => {
  // ecs-cost-intelligence does not ship; the clauses that route to it ("for
  // cost/TCO use ecs-cost-intelligence") are not indexed, so "cost intelligence"
  // never reaches ecs-operation-review; "ecs" alone still finds every ECS skill.
  assert.ok(!shown('cost intelligence').all.includes('ecs-operation-review'));
  assert.ok(!shown('kubernetes').all.includes('ecs-architect'));
});

test('M2: both platforms are matches for a one-word task', () => {
  assert.deepEqual(shown('llm').rows.slice(0, 2), ['eks-genai', 'ecs-genai']);
  assert.deepEqual(shown('harden').rows.slice(0, 2), ['eks-security', 'ecs-security']);
});

test('M4: no part-word hits outside the name, no Best match from a part word', () => {
  assert.ok(!shown('ai').all.includes('eks-security'), 'ai from "against"');
  assert.ok(!shown('cis').all.includes('ecs-devops'), 'cis from "decisions"');
  assert.ok(!shown('rag').all.includes('eks-cost-intelligence'), 'rag from "storage"');
  const net = search(index, 'net') as Hit[];
  assert.ok(net[0].score < 20, 'net is not a Best match');
  assert.equal(shown('e').total, 0);
});

test('M5: "skill" and "skills" are stop words', () => {
  assert.deepEqual(shown('eks skills').all, shown('eks').all);
  assert.deepEqual(shown('amazon ecs').all, shown('ecs').all);
  assert.deepEqual(shown('amazon eks').all, shown('eks').all);
});

test('FB-1 and U2: a stop-word-only query shows the whole catalogue, EKS first, no Best match', () => {
  const order = {eks: 0, ecs: 1, general: 2} as Record<string, number>;
  const want = [...manifest]
    .sort((a: {name: string; group: string}, b: {name: string; group: string}) =>
      order[a.group] - order[b.group] || a.name.localeCompare(b.name))
    .map((s: {name: string}) => s.name);
  for (const query of ['aws skills', 'skills']) {
    const hits = search(index, query) as Hit[];
    assert.deepEqual(hits.map((h) => h.skill.name), want, query);
    assert.equal(hits[0].skill.name.slice(0, 4), 'eks-', query);
    assert.ok(hits.every((h) => h.score === 0 && !h.passing), query);
  }
});

const ports = readdirSync(new URL('../../../../devops-agent/', here), {withFileTypes: true})
  .filter((d) => d.isDirectory())
  .map((d) => d.name)
  .sort();

test('AG-1 and U3: "aws agents" puts apex, then the DevOps Agent ports, ahead of eks-mcp-server', () => {
  const r = shown('aws agents');
  assert.deepEqual(r.rows, ['apex', ...ports, 'eks-mcp-server']);
  assert.ok((search(index, 'aws agents') as Hit[])[0].score < 20, 'no Best match');
});

test('U3: an agent query marks the ports, which open their DevOps Agent pages', () => {
  for (const query of ['aws agents', 'devops agent']) {
    const hits = search(index, query) as Hit[];
    assert.deepEqual(hits.filter((h) => h.port).map((h) => h.skill.name), ports, query);
  }
  assert.ok((search(index, 'eks recon') as Hit[]).every((h) => !h.port), 'not an agent query');
});

test('AG-2 and U4: "devops agent" finds apex and the ports; "devops" alone finds only ecs-devops', () => {
  assert.deepEqual(shown('devops agent').rows, ['apex', ...ports]);
  assert.deepEqual(shown('devops').all, ['ecs-devops']);
});

test('S-R2-4: "running" and "run" find the same skills', () => {
  assert.deepEqual(shown('running').all, shown('run').all);
  assert.ok(shown('run').total > 0);
});

test('392-1: "on" is a stop word; a summary word is a strong match', () => {
  assert.deepEqual(queryWords('ecs on fargate'), queryWords('ecs fargate'));
  assert.ok(!(search(index, 'vllm') as Hit[])[0].passing, 'vllm is in eks-genai\'s summary');
});

test('S1: ties put EKS before ECS', () => {
  assert.deepEqual(shown('recon').rows, ['eks-recon', 'ecs-recon']);
  assert.deepEqual(shown('operation review').rows, ['eks-operation-review', 'ecs-operation-review']);
});

test('S-R2-6: text after a route-away phrase is not indexed', () => {
  assert.ok(!shown('windows').all.includes('dotnet-aws-ecs'), 'dotnet-aws-ecs: "NOT for Windows containers"');
});

test('Site search: "deploy a cluster" also shows ecs-build, which builds ECS clusters', () => {
  // skills/ecs-build/SKILL.md:3 "apply-ready code for clusters, services, and task definitions".
  assert.ok(shown('deploy a cluster').rows.includes('ecs-build'));
});

test('Site search: filler words do not hide the task word', () => {
  // eks-ingress-migration: "Assess a live EKS cluster's NGINX/Ingress estate" (skills/eks-ingress-migration/SKILL.md:3).
  assert.ok(shown('how do i set up ingress').rows.includes('eks-ingress-migration'));
  // ecs-architect: "Fargate vs ECS on EC2 vs Managed Instances" (skills/ecs-architect/SKILL.md:3).
  assert.ok(shown('spin up fargate').rows.includes('ecs-architect'));
});

test('S-R2-6: "." stays inside a word', () => {
  const hits: Hit[] = search(index, '32');
  assert.ok(hits.every((h) => h.score === 0), '"32" is not a word of "1.32"');
  assert.equal(hits.length, manifest.length, 'no word matched: the whole catalogue');
});
