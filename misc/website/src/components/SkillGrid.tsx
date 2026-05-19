import type {ReactNode} from 'react';
import Link from '@docusaurus/Link';
import Heading from '@theme/Heading';
import skills from '@site/static/manifests/skills.json';

type Skill = {
  name: string;
  description: string;
  path: string;
};

function firstSentence(text: string): string {
  const trimmed = text.trim();
  const match = trimmed.match(/^(.+?[.!?])(\s|$)/);
  return match ? match[1] : trimmed;
}

function SkillCard({skill}: {skill: Skill}): ReactNode {
  return (
    <div className="col col--4 margin-bottom--lg">
      <div className="card" style={{height: '100%'}}>
        <div className="card__header">
          <Heading as="h3" style={{marginBottom: 0}}>
            <code>{skill.name}</code>
          </Heading>
        </div>
        <div className="card__body">
          <p>{firstSentence(skill.description)}</p>
        </div>
        <div className="card__footer">
          <Link
            className="button button--primary button--block"
            to={skill.path}
          >
            Open
          </Link>
        </div>
      </div>
    </div>
  );
}

export default function SkillGrid(): ReactNode {
  return (
    <section className="container margin-bottom--xl">
      <Heading as="h2" className="text--center margin-bottom--lg">
        Skills
      </Heading>
      <div className="row">
        {(skills as Skill[]).map((skill) => (
          <SkillCard key={skill.name} skill={skill} />
        ))}
      </div>
    </section>
  );
}

export const skillCount = (skills as Skill[]).length;
