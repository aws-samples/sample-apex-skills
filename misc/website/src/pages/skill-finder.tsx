import type {ReactNode} from 'react';
import Link from '@docusaurus/Link';
import Layout from '@theme/Layout';
import SkillFinder from '@site/src/components/SkillFinder';

export default function SkillFinderPage(): ReactNode {
  return (
    <Layout
      title="Skill finder: EKS and ECS skills"
      description="Search and filter every APEX skill for Amazon EKS and Amazon ECS by platform, eval score and AWS DevOps Agent support, then open its docs or its install command.">
      <main className="container margin-vert--lg">
        <h1>Skill finder</h1>
        <p>
          Every APEX skill, read from its <code>SKILL.md</code>. Filter by
          platform, or search the skill descriptions. Not sure where to start?
          The <Link to="/docs/skills/general/apex/">apex router</Link> picks a
          skill for you.
        </p>
        <SkillFinder />
      </main>
    </Layout>
  );
}
