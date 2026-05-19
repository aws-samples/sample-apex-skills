import type {ReactNode} from 'react';
import clsx from 'clsx';
import Link from '@docusaurus/Link';
import useDocusaurusContext from '@docusaurus/useDocusaurusContext';
import Layout from '@theme/Layout';
import Heading from '@theme/Heading';

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
          <Heading as="h2">MIT-0</Heading>
          <p>Permissive license. Use it freely.</p>
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
          <Heading as="h2">EKS-focused</Heading>
          <p>Curated by senior AWS Solutions Architects.</p>
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
      </main>
    </Layout>
  );
}
