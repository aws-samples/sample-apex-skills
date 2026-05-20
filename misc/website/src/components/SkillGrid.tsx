import type {ReactNode} from 'react';
import Link from '@docusaurus/Link';
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
    <div className="apex-card">
      <div className="apex-card__header">{skill.name}</div>
      <div className="apex-card__body">{firstSentence(skill.description)}</div>
      <div className="apex-card__footer">
        <Link to={skill.path} className="apex-card__btn">
          Open →
        </Link>
      </div>
    </div>
  );
}

export default function SkillGrid(): ReactNode {
  return (
    <section className="apex-section">
      <h2 className="apex-section__title">Skills</h2>
      <div className="apex-section__grid">
        {(skills as Skill[]).map((skill) => (
          <SkillCard key={skill.name} skill={skill} />
        ))}
      </div>
    </section>
  );
}

export const skillCount = (skills as Skill[]).length;
