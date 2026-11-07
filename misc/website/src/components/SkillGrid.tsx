import type {ReactNode} from 'react';
import Link from '@docusaurus/Link';
import useBrokenLinks from '@docusaurus/useBrokenLinks';
import {JOBS, JOB_TREE, PLATFORM_LABEL, SKILLS, skillHref, type CatalogSkill, type JobNode} from './skillCatalog';

// Skills grouped by the job they do (JOB_TREE), in the order a project meets them.
// compact: name and one line (home page); full: also what it is not for and
// what you get (the /skills page).

function Entry({skill, detail}: {skill: CatalogSkill; detail: 'compact' | 'full'}): ReactNode {
  return (
    <li className="apex-job__skill">
      <Link to={skillHref(skill)} className="apex-job__link">
        <code>{skill.name}</code>
        <span className={`apex-tag apex-tag--${skill.platform}`}>{PLATFORM_LABEL[skill.platform]}</span>
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

type HeadingTag = 'h2' | 'h3' | 'h4' | 'h5';

function heading(level: number): HeadingTag {
  return `h${Math.min(level, 5)}` as HeadingTag;
}

function sortSkills(list: CatalogSkill[]): CatalogSkill[] {
  return [...list].sort((a, b) => ORDER.indexOf(a.platform) - ORDER.indexOf(b.platform) || a.name.localeCompare(b.name));
}

function nodeSkills(node: JobNode, skills: CatalogSkill[]): CatalogSkill[] {
  if ('job' in node) return skills.filter((s) => s.job === node.job);
  return node.children.flatMap((child) => nodeSkills(child, skills));
}

function Node({
  node,
  skills,
  detail,
  level,
}: {
  node: JobNode;
  skills: CatalogSkill[];
  detail: 'compact' | 'full';
  level: number;
}): ReactNode {
  if (nodeSkills(node, skills).length === 0) return null;
  const Heading = heading(level);
  if ('job' in node) {
    const job = JOBS.find((j) => j.id === node.job)!;
    const list = sortSkills(skills.filter((s) => s.job === node.job));
    return (
      <section className="apex-job" aria-labelledby={`job-${job.id}`}>
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
  }
  return (
    <section className="apex-stage" aria-labelledby={`group-${node.id}`}>
      <div className="apex-stage__head">
        <Heading id={`group-${node.id}`} className="apex-stage__title">
          {node.title}
        </Heading>
        <p className="apex-job__line">{node.line}</p>
      </div>
      {node.children.map((child) => (
        <Node key={'job' in child ? child.job : child.id} node={child} skills={skills} detail={detail} level={level + 1} />
      ))}
    </section>
  );
}

function collectIds(nodes: JobNode[]): string[] {
  return nodes.flatMap((n) => ('job' in n ? [`job-${n.job}`] : [`group-${n.id}`, ...collectIds(n.children)]));
}

export default function SkillGrid({skills = SKILLS, detail = 'compact', headingLevel = 2}: Props): ReactNode {
  // Register the job anchors so the build's broken-anchor check sees links
  // such as /skills#job-design from skill pages.
  const brokenLinks = useBrokenLinks();
  for (const id of collectIds(JOB_TREE)) brokenLinks.collectAnchor(id);
  return (
    <div className={`apex-jobs apex-jobs--${detail}`}>
      {JOB_TREE.map((node) => (
        <Node key={'job' in node ? node.job : node.id} node={node} skills={skills} detail={detail} level={headingLevel} />
      ))}
    </div>
  );
}

export {skillCount} from './skillCatalog';
