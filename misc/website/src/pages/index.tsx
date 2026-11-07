import type {ReactNode} from 'react';
import Link from '@docusaurus/Link';
import Layout from '@theme/Layout';
import useBrokenLinks from '@docusaurus/useBrokenLinks';
import SkillFinder from '@site/src/components/SkillFinder';
import SkillGrid from '@site/src/components/SkillGrid';
import InstallBlock from '@site/src/components/InstallBlock';
import {SKILLS, platformCounts, skillCount} from '@site/src/components/skillCatalog';

const counts = platformCounts(SKILLS);

export default function Home(): ReactNode {
  useBrokenLinks().collectAnchor('install');
  return (
    <Layout
      title="EKS and ECS skills"
      description={`${skillCount} open-source agent skills for Amazon EKS and Amazon ECS: design, build, assess, upgrade and secure clusters from Claude Code, Kiro CLI or any Agent Skills harness.`}
    >
      <main className="apex-home">
        <header className="apex-home__hero">
          <div className="apex-wrap">
            <h1 className="apex-home__title">EKS and ECS skills</h1>
            <p className="apex-home__pitch">
              Skills that let your coding agent design, build, review and upgrade Amazon EKS and Amazon ECS. Tell it
              the job; it brings the checks, the scripts and the AWS guidance.
            </p>
            <SkillFinder variant="hero" />
            <p className="apex-home__facts">
              {counts.eks} EKS, {counts.ecs} ECS and {counts.general} general skills. Open source under MIT-0, built by
              AWS Solutions Architects, TAMs and ProServe.
            </p>
          </div>
        </header>

        <section className="apex-home__section" aria-labelledby="browse">
          <div className="apex-wrap">
            <div className="apex-home__sectionhead">
              <h2 id="browse">Browse by job</h2>
              <Link to="/skills">Compare all {skillCount} skills</Link>
            </div>
            <SkillGrid skills={SKILLS.filter((s) => s.name !== 'apex')} headingLevel={3} />
          </div>
        </section>

        <section className="apex-home__section apex-home__section--install" id="install" aria-labelledby="install-title">
          <div className="apex-wrap apex-home__split">
            <div>
              <h2 id="install-title">Install</h2>
              <p>
                Skills are folders of instructions and scripts that your agent loads when a task needs them.
                Assessments are read-only, and no skill changes your account or cluster without your confirmation.
              </p>
            </div>
            <InstallBlock />
          </div>
        </section>

        <section className="apex-home__section" aria-labelledby="router">
          <div className="apex-wrap">
            <div className="apex-router">
              <h2 id="router">Not sure which skill? Start with /apex</h2>
              <p>
                Describe the task in your own words. The router reads your request and workspace, asks only what it
                still needs, loads the skill that fits, and suggests the next one when you are done.
              </p>
              <pre className="apex-router__example">
                <code>/apex plan the upgrade of my prod EKS cluster to the next version</code>
              </pre>
              <Link className="apex-button" to="/docs/skills/general/apex/">
                How the router works
              </Link>
            </div>
          </div>
        </section>
      </main>
    </Layout>
  );
}
