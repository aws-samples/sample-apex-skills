import type {ReactNode} from 'react';
import Link from '@docusaurus/Link';
import useBrokenLinks from '@docusaurus/useBrokenLinks';
import {JOBS, PLATFORM_LABEL, SKILLS, skillHref, type CatalogSkill} from './skillCatalog';

// Skills grouped by the job they do, in the order a project meets them.
// compact: name and one line (home page); full: also what it is not for and
// what you get (the /skills page).

function Entry({skill, detail}: {skill: CatalogSkill; detail: 'compact' | 'full'}): ReactNode {
  return (
    <li className="apex-job__skill">
      <Link to={skillHref(skill)} className="apex-job__link">
        <code>{skill.name}</code>
        <span className={`apex-tag apex-tag--${skill.group}`}>{PLATFORM_LABEL[skill.group]}</span>
      </Link>
      <p className="apex-job__use">{skill.use}</p>
      {detail === 'full' && (skill.output || skill.notFor) && (
        <dl className="apex-job__facts">
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
        </dl>
      )}
    </li>
  );
}

// EKS first, then ECS, then skills for any platform.
const ORDER = ['eks', 'ecs', 'general'];

type Props = {
  skills?: CatalogSkill[];
  detail?: 'compact' | 'full';
  headingLevel?: 2 | 3;
};

export default function SkillGrid({skills = SKILLS, detail = 'compact', headingLevel = 2}: Props): ReactNode {
  const Heading = headingLevel === 2 ? 'h2' : 'h3';
  // Register the job anchors so the build's broken-anchor check sees links
  // such as /skills#job-design from skill pages.
  const brokenLinks = useBrokenLinks();
  for (const job of JOBS) brokenLinks.collectAnchor(`job-${job.id}`);
  return (
    <div className={`apex-jobs apex-jobs--${detail}`}>
      {JOBS.map((job) => {
        const list = skills
          .filter((s) => s.job === job.id)
          .sort((a, b) => ORDER.indexOf(a.group) - ORDER.indexOf(b.group) || a.name.localeCompare(b.name));
        if (list.length === 0) return null;
        return (
          <section key={job.id} className="apex-job" aria-labelledby={`job-${job.id}`}>
            <div className="apex-job__head">
              <Heading id={`job-${job.id}`} className="apex-job__title">
                {job.title}
              </Heading>
              <p className="apex-job__line">{job.line}</p>
            </div>
            <ul className="apex-job__list">
              {list.map((skill) => (
                <Entry key={skill.name} skill={skill} detail={detail} />
              ))}
            </ul>
          </section>
        );
      })}
    </div>
  );
}

export {skillCount} from './skillCatalog';
