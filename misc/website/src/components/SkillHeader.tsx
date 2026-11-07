import type {ReactNode} from 'react';
import Link from '@docusaurus/Link';
import {JOBS, PLATFORM_LABEL, SKILLS, jobLabel} from './skillCatalog';

// The short block at the top of a skill page: what the skill is for, what it
// is not for, what you get and how to run it. The SKILL.md body the agent
// reads stays below, unchanged. Docusaurus already emits the page's
// BreadcrumbList JSON-LD (plugin-content-docs structuredDataUtils), so none
// is added here.

const SKILL_PAGE = /^\/docs\/skills\/(eks|ecs|general)\/([^/]+)\/?$/;

export function skillForPermalink(permalink: string, baseUrl: string) {
  const path = permalink.startsWith(baseUrl) ? `/${permalink.slice(baseUrl.length)}` : permalink;
  const match = path.match(SKILL_PAGE);
  if (!match) return undefined;
  return SKILLS.find((s) => s.name === match[2] && s.group === match[1]);
}

export default function SkillHeader({permalink, baseUrl}: {permalink: string; baseUrl: string}): ReactNode {
  const skill = skillForPermalink(permalink, baseUrl);
  if (!skill) return null;
  const job = JOBS.find((j) => j.id === skill.job);
  return (
    <aside className="apex-skillhead" aria-label="Skill at a glance">
      <p className="apex-skillhead__where">
        <span className={`apex-tag apex-tag--${skill.platform}`}>{PLATFORM_LABEL[skill.platform]}</span>
        {job && (
          <Link to={`/skills#job-${job.id}`} className="apex-skillhead__job">
            {jobLabel(job)}
          </Link>
        )}
      </p>
      <p className="apex-skillhead__use">{skill.use}</p>
      <dl className="apex-skillhead__facts">
        {skill.output && (
          <>
            <dt>You get</dt>
            <dd>{skill.output}</dd>
          </>
        )}
        {skill.notFor && (
          <>
            <dt>Not for</dt>
            <dd>{skill.notFor}</dd>
          </>
        )}
        <dt>Run it</dt>
        <dd>
          Once <Link to="/#install">installed</Link> from main: <code>/{skill.name}</code> in Claude Code; in Kiro CLI,
          ask for it by name or use <code>/apex</code>.
        </dd>
      </dl>
    </aside>
  );
}
