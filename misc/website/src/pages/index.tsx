import type {ReactNode} from 'react';
import clsx from 'clsx';
import Link from '@docusaurus/Link';
import useDocusaurusContext from '@docusaurus/useDocusaurusContext';
import Layout from '@theme/Layout';
import Heading from '@theme/Heading';
import SkillGrid, {skillCount} from '@site/src/components/SkillGrid';

function HeroBanner() {
  const {siteConfig} = useDocusaurusContext();
  return (
    <header className={clsx('hero', 'hero--primary')}>
      <div className="container">
        <Heading as="h1" className="hero__title">
          {siteConfig.title}
        </Heading>
        <p className="hero__subtitle">{siteConfig.tagline}</p>
        <div>
          <Link className="button button--secondary button--lg" to="/docs/skills">
            Browse Skills
          </Link>
          <span style={{display: 'inline-block', width: '0.75rem'}} />
          <Link
            className="button button--outline button--secondary button--lg"
            href="https://github.com/aws-samples/sample-apex-skills"
          >
            GitHub
          </Link>
        </div>
      </div>
    </header>
  );
}

function StatStrip() {
  return (
    <section className="container margin-top--xl margin-bottom--lg">
      <div className="row">
        <div className="col col--4 text--center">
          <Heading as="h2">{skillCount} skills</Heading>
          <p>Curated EKS platform-engineering knowledge, ready to load.</p>
        </div>
        <div className="col col--4 text--center">
          <Heading as="h2">Agent Skills</Heading>
          <p>
            Compatible with{' '}
            <Link href="https://agentskills.io/">agentskills.io</Link>, Claude
            Code, and Kiro CLI.
          </p>
        </div>
        <div className="col col--4 text--center">
          <Heading as="h2">MIT-0</Heading>
          <p>Authored by AWS Solutions Architects, TAMs, and ProServe.</p>
        </div>
      </div>
    </section>
  );
}

function SteeringTeaser() {
  return (
    <section className="container margin-bottom--xl">
      <div className="row">
        <div className="col col--8 col--offset-2 text--center">
          <Heading as="h2">Combine skills into phased workflows</Heading>
          <p>
            <strong>Steering</strong> workflows give the agent structure — an
            ordered sequence of phases, each pulling in the right skill at the
            right time.
          </p>
          <Link className="button button--primary button--lg" to="/docs/steering">
            Browse Steering Workflows
          </Link>
        </div>
      </div>
    </section>
  );
}

export default function Home(): ReactNode {
  const {siteConfig} = useDocusaurusContext();
  return (
    <Layout title={siteConfig.title} description={siteConfig.tagline}>
      <HeroBanner />
      <main>
        <StatStrip />
        <SkillGrid />
        <SteeringTeaser />
      </main>
    </Layout>
  );
}
