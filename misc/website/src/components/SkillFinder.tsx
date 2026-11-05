import {useEffect, useMemo, useState, type ReactNode} from 'react';
import Link from '@docusaurus/Link';
import skills from '@site/static/manifests/skill-finder.json';

// One row of static/manifests/skill-finder.json, written by
// misc/build-skill-finder.py from the SKILL.md frontmatter.
export type FinderSkill = {
  name: string;
  summary: string;
  description: string;
  group: 'eks' | 'ecs' | 'general';
  path: string;
  allowedTools: boolean;
  upstream: boolean;
  devopsAgent: boolean;
  eval: {score: number | null; grade: string | null} | null;
};

const allSkills = skills as FinderSkill[];

const GROUP_LABELS: Record<FinderSkill['group'], string> = {
  eks: 'Amazon EKS',
  ecs: 'Amazon ECS',
  general: 'General',
};

type Flag = 'devopsAgent' | 'evaluated' | 'upstream';

const FLAG_LABELS: Record<Flag, string> = {
  devopsAgent: 'AWS DevOps Agent port',
  evaluated: 'Has an eval score',
  upstream: 'Synced from upstream',
};

function matches(skill: FinderSkill, query: string): boolean {
  if (!query) return true;
  const haystack = `${skill.name} ${skill.description}`.toLowerCase();
  return query
    .toLowerCase()
    .split(/\s+/)
    .filter(Boolean)
    .every((word) => haystack.includes(word));
}

function hasFlag(skill: FinderSkill, flag: Flag): boolean {
  if (flag === 'evaluated') return skill.eval !== null && skill.eval.score !== null;
  return skill[flag];
}

function SkillResult({skill}: {skill: FinderSkill}): ReactNode {
  return (
    <li className="apex-card apex-finder__card">
      <div className="apex-card__header">
        {skill.name}
        {skill.eval?.grade && (
          <span
            className={`apex-eval__grade apex-eval__grade--${skill.eval.grade}`}
            title={`Eval score ${skill.eval.score}`}>
            {skill.eval.grade}
          </span>
        )}
      </div>
      <div className="apex-finder__tags">
        <span className="apex-finder__tag">{GROUP_LABELS[skill.group]}</span>
        {skill.devopsAgent && <span className="apex-finder__tag">DevOps Agent port</span>}
        {skill.upstream && <span className="apex-finder__tag">Synced from upstream</span>}
      </div>
      <div className="apex-card__body">{skill.summary}</div>
      <div className="apex-card__footer apex-finder__actions">
        <Link to={`${skill.path}/`} className="apex-card__btn">
          Docs →
        </Link>
        <Link to={`/install/?skill=${encodeURIComponent(skill.name)}`} className="apex-card__btn">
          Install →
        </Link>
      </div>
    </li>
  );
}

export default function SkillFinder(): ReactNode {
  const [query, setQuery] = useState('');
  const [group, setGroup] = useState<FinderSkill['group'] | 'all'>('all');
  const [flags, setFlags] = useState<Flag[]>([]);

  // Deep links such as /skill-finder?group=eks or ?q=upgrade.
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const g = params.get('group');
    if (g === 'eks' || g === 'ecs' || g === 'general') setGroup(g);
    const q = params.get('q');
    if (q) setQuery(q);
  }, []);

  const results = useMemo(
    () =>
      allSkills.filter(
        (s) =>
          (group === 'all' || s.group === group) &&
          flags.every((f) => hasFlag(s, f)) &&
          matches(s, query),
      ),
    [query, group, flags],
  );

  const toggleFlag = (flag: Flag) =>
    setFlags((current) =>
      current.includes(flag) ? current.filter((f) => f !== flag) : [...current, flag],
    );

  return (
    <div className="apex-finder">
      <div className="apex-finder__controls">
        <label className="apex-finder__search">
          <span className="apex-finder__label">Search</span>
          <input
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="for example: upgrade, terraform, cost, ingress"
          />
        </label>
        <fieldset className="apex-finder__facet">
          <legend className="apex-finder__label">Platform</legend>
          {(['all', 'eks', 'ecs', 'general'] as const).map((g) => (
            <label key={g}>
              <input
                type="radio"
                name="apex-finder-group"
                checked={group === g}
                onChange={() => setGroup(g)}
              />
              {g === 'all' ? 'All' : GROUP_LABELS[g]}
            </label>
          ))}
        </fieldset>
        <fieldset className="apex-finder__facet">
          <legend className="apex-finder__label">Only</legend>
          {(Object.keys(FLAG_LABELS) as Flag[]).map((flag) => (
            <label key={flag}>
              <input
                type="checkbox"
                checked={flags.includes(flag)}
                onChange={() => toggleFlag(flag)}
              />
              {FLAG_LABELS[flag]}
            </label>
          ))}
        </fieldset>
      </div>
      <p className="apex-finder__count" aria-live="polite">
        {results.length} of {allSkills.length} skills
      </p>
      <ul className="apex-section__grid apex-finder__results">
        {results.map((s) => (
          <SkillResult key={s.name} skill={s} />
        ))}
      </ul>
    </div>
  );
}
