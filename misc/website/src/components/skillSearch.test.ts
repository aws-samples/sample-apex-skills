// Ranking table test for the skill finder, over the real manifest.
// Run from misc/website: node --experimental-strip-types src/components/skillSearch.test.ts
// --experimental-strip-types needs Node 22.6 or later (package.json engines says >=20), and no
// npm script runs this test.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';

const here = new URL('.', import.meta.url);
const {buildIndex, search} = await import(new URL('skillSearch.ts', here).href);
const manifest = JSON.parse(readFileSync(new URL('../../static/manifests/skills.json', here), 'utf8'));
// The hand-written use lines stand in for the summary, as in skillCatalog.ts.
const catalog = readFileSync(new URL('skillCatalog.ts', here), 'utf8');
const uses = Object.fromEntries(
  [...catalog.matchAll(/'?([a-z-]+)'?: \{\s*job: '[a-z]+',\s*use: '([^']+)'/g)].map((m) => [m[1], m[2]]),
);
const index = buildIndex(manifest.map((s: {name: string}) => ({...s, use: uses[s.name]})));

type Hit = {skill: {name: string}; score: number; passing: boolean};

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
  // M3: Enter opens the row shown first.
  ['ecs on fargate', 'dotnet-aws-ecs'],
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
];

for (const [query, want, most] of FIRST) {
  test(`"${query}" shows ${want} first`, () => {
    const r = shown(query);
    assert.equal(r.first, want, `rows: ${r.rows.join(', ')}`);
    if (most !== undefined) assert.ok(r.total <= most, `${r.total} results`);
  });
}

test('M1: a skill that only routes away is not matched', () => {
  // R2-M3 keeps a clause that names a skill not in the manifest, so
  // ecs-operation-review's "for cost/TCO use ecs-cost-intelligence" is a mention only.
  assert.ok((search(index, 'ecs cost intelligence') as Hit[]).every((h) => h.passing && h.score < 20));
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
  assert.equal(shown('skills').total, 0);
});

test('S1: ties put EKS before ECS', () => {
  assert.deepEqual(shown('recon').rows, ['eks-recon', 'ecs-recon']);
  assert.deepEqual(shown('operation review').rows, ['eks-operation-review', 'ecs-operation-review']);
});

test('S-R2-6: text after a route-away phrase is not indexed', () => {
  assert.ok(!shown('windows').all.includes('dotnet-aws-ecs'), 'dotnet-aws-ecs: "NOT for Windows containers"');
});

test('S-R2-6: "." stays inside a word', () => {
  assert.equal(shown('32').total, 0, '"32" is not a word of "1.32"');
});
