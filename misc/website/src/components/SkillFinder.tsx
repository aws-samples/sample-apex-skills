import {useEffect, useId, useMemo, useRef, useState, type ReactNode} from 'react';
import Link from '@docusaurus/Link';
import {useHistory} from '@docusaurus/router';
import {useBaseUrlUtils} from '@docusaurus/useBaseUrl';
import {
  SKILLS,
  PLATFORM_LABEL,
  platformCounts,
  portHref,
  skillHref,
  type Platform,
} from './skillCatalog';
import {buildIndex, queryWords, search, type Hit} from './skillSearch';
import SkillGrid from './SkillGrid';

const INDEX = buildIndex(SKILLS);
const EXAMPLES = ['upgrade check', 'ingress', 'cost', 'terraform', 'security', 'gpu'];

function PlatformTag({platform}: {platform: Platform}): ReactNode {
  return <span className={`apex-tag apex-tag--${platform}`}>{PLATFORM_LABEL[platform]}</span>;
}

// An agent query ("aws agents", "devops agent") opens a port's AWS DevOps Agent page.
function hitHref(hit: Hit): string {
  return hit.port ? portHref(hit.skill.name) : skillHref(hit.skill);
}

function PortTag({hit}: {hit: Hit}): ReactNode {
  return hit.port ? <span className="apex-tag">DevOps Agent</span> : null;
}

function TopHit({hit}: {hit: Hit}): ReactNode {
  const {skill} = hit;
  return (
    <Link className="apex-tophit" to={hitHref(hit)}>
      <span className="apex-tophit__label">Best match</span>
      <span className="apex-tophit__name">
        <code>{skill.name}</code>
        <PlatformTag platform={skill.platform} />
        <PortTag hit={hit} />
      </span>
      <span className="apex-tophit__use">{skill.use}</span>
      {skill.output && <span className="apex-tophit__output">You get: {skill.output}</span>}
    </Link>
  );
}

function HitRow({hit}: {hit: Hit}): ReactNode {
  const {skill} = hit;
  return (
    <li>
      <Link className="apex-hit" to={hitHref(hit)}>
        <code className="apex-hit__name">{skill.name}</code>
        <PlatformTag platform={skill.platform} />
        <PortTag hit={hit} />
        <span className="apex-hit__use">{skill.use}</span>
      </Link>
    </li>
  );
}

type Props = {
  // hero: the home page search, a few results and a link to the full page;
  // page: the /skills catalogue, with platform filters and every result.
  variant: 'hero' | 'page';
};

export default function SkillFinder({variant}: Props): ReactNode {
  const isPage = variant === 'page';
  const inputId = useId();
  const history = useHistory();
  const {withBaseUrl} = useBaseUrlUtils();
  const rootRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const [query, setQuery] = useState('');
  const [platform, setPlatform] = useState<Platform | 'all'>('all');
  const [reserve, setReserve] = useState<number | undefined>(undefined);

  // A shared /skills?q=<query> link is read once on arrival. The page keeps
  // the catalogue's height, at most one screen, until the visitor acts, so
  // the footer does not jump into view.
  useEffect(() => {
    if (!isPage) return;
    const q = new URLSearchParams(window.location.search).get('q');
    if (!q) return;
    setReserve(Math.min(rootRef.current?.offsetHeight ?? 0, window.innerHeight));
    setQuery(q);
  }, [isPage]);

  const inPlatform = useMemo(
    () => (platform === 'all' ? SKILLS : SKILLS.filter((s) => s.platform === platform)),
    [platform],
  );
  const hits = useMemo(() => {
    const all = search(INDEX, query);
    return platform === 'all' ? all : all.filter((h) => h.skill.platform === platform);
  }, [query, platform]);
  const counts = useMemo(() => platformCounts(SKILLS), []);

  // A stop-word-only query ("aws skills") lists every skill in the hero, EKS
  // first; the page keeps its grid, the catalogue in its normal order.
  const keyWords = queryWords(query).length > 0;
  const searching = keyWords || (!isPage && hits.length > 0);
  // A clear winner: the query is in the skill's name and it outscores the next hit.
  const top = hits[0] && hits[0].score >= 20 && (!hits[1] || hits[0].score > hits[1].score) ? hits[0] : null;
  // Strong hits match every word in the name or summary; the others only
  // mention a word somewhere in their long description, so they sit apart.
  const strong = hits.filter((h) => !h.passing);
  const mentions = strong.length > 0 ? hits.filter((h) => !strong.includes(h)) : [];
  const main = (strong.length > 0 ? strong : hits).filter((h) => h !== top);
  const shown = isPage ? main : main.slice(0, top ? 4 : 5);

  // Enter opens the first result shown.
  const openTop = () => {
    const first = top ?? main[0] ?? hits[0];
    if (first) history.push(withBaseUrl(hitHref(first)));
  };

  return (
    <div
      ref={rootRef}
      className={`apex-finder apex-finder--${variant}`}
      role="search"
      style={reserve ? {minHeight: reserve} : undefined}
    >
      <label className="apex-finder__label" htmlFor={inputId}>
        What are you working on?
      </label>
      <div className="apex-finder__box">
        <svg className="apex-finder__icon" viewBox="0 0 20 20" aria-hidden="true">
          <circle cx="8.5" cy="8.5" r="5.5" fill="none" stroke="currentColor" strokeWidth="2" />
          <path d="M13 13l4.5 4.5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
        </svg>
        <input
          ref={inputRef}
          id={inputId}
          className="apex-finder__input"
          type="search"
          autoComplete="off"
          spellCheck={false}
          placeholder="What are you working on?"
          value={query}
          onChange={(e) => {
            setReserve(undefined);
            setQuery(e.target.value);
          }}
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              e.preventDefault();
              openTop();
            }
          }}
        />
      </div>

      {isPage && (
        <div className="apex-facets" role="group" aria-label="Platform">
          {(['all', 'eks', 'ecs', 'general'] as const).map((p) => (
            <button
              key={p}
              type="button"
              className="apex-facet"
              aria-pressed={platform === p}
              onClick={() => {
                setReserve(undefined);
                setPlatform(p);
              }}
            >
              {p === 'all' ? 'All' : PLATFORM_LABEL[p]}
              <span className="apex-facet__count">{p === 'all' ? SKILLS.length : counts[p]}</span>
            </button>
          ))}
        </div>
      )}

      <p className="apex-finder__status" aria-live="polite">
        {searching
          ? hits.length === 0
            ? (
                <>
                  No skill matches every word of &ldquo;{query.trim()}&rdquo;. Try one key word,{' '}
                  <Link to="/skills" onClick={() => setQuery('')}>
                    browse every skill
                  </Link>
                  , or describe the task to the <Link to="/docs/skills/general/apex/">apex router</Link>.
                </>
              )
            : keyWords
              ? `${hits.length - mentions.length} ${
                  hits.length - mentions.length === 1 ? 'skill matches' : 'skills match'
                }${mentions.length ? `, ${mentions.length} more mention it` : ''}. Enter opens the first one.`
              : `All ${hits.length} skills, EKS first. Enter opens the first one.`
          : isPage
            ? `${inPlatform.length} skills`
            : null}
      </p>

      {!searching && (
        <div className="apex-finder__examples">
          <span>Try</span>
          {EXAMPLES.map((example) => (
            <button
              key={example}
              type="button"
              className="apex-chip"
              onClick={() => {
                setQuery(example);
                inputRef.current?.focus();
              }}
            >
              {example}
            </button>
          ))}
        </div>
      )}

      {searching && hits.length > 0 && (
        <div className="apex-finder__results">
          {top && <TopHit hit={top} />}
          {shown.length > 0 && (
            <ul className="apex-hits">
              {shown.map((hit) => (
                <HitRow key={hit.skill.name} hit={hit} />
              ))}
            </ul>
          )}
          {isPage && mentions.length > 0 && (
            <details className="apex-mentions">
              <summary>
                {mentions.length} more {mentions.length === 1 ? 'skill mentions' : 'skills mention'} &ldquo;
                {query.trim()}&rdquo; in passing
              </summary>
              <ul className="apex-hits">
                {mentions.map((hit) => (
                  <HitRow key={hit.skill.name} hit={hit} />
                ))}
              </ul>
            </details>
          )}
          {!isPage && hits.length > (top ? 1 : 0) + shown.length && (
            <Link className="apex-finder__more" to={`/skills?q=${encodeURIComponent(query.trim())}`}>
              See all {hits.length} results
            </Link>
          )}
        </div>
      )}

      {isPage && !searching && <SkillGrid skills={inPlatform} detail="full" />}
    </div>
  );
}
