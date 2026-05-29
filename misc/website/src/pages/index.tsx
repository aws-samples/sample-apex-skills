import type {ReactNode} from 'react';
import Link from '@docusaurus/Link';
import useDocusaurusContext from '@docusaurus/useDocusaurusContext';
import Layout from '@theme/Layout';
import {skillCount} from '@site/src/components/SkillGrid';

function HeroBanner() {
  return (
    <header className="apex-hero">
      <div className="apex-hero__glow" />
      <div className="apex-hero__container">
        <span className="apex-hero__badge">Open Source · MIT-0</span>
        <h1 className="apex-hero__title">APEX Skills</h1>
        <p className="apex-hero__subtitle">
          Platform engineering with agents — curated AWS skills delivered through
          your AI coding agent
        </p>
        <p className="apex-hero__meta">
          {skillCount} skills · MIT-0 · agentskills.io · Claude Code · Kiro CLI
        </p>
        <div className="apex-hero__actions">
          <Link className="apex-hero__cta apex-hero__cta--primary" to="/docs/getting-started">
            Get Started
          </Link>
          <Link
            className="apex-hero__cta apex-hero__cta--secondary"
            href="https://github.com/aws-samples/sample-apex-skills"
          >
            GitHub →
          </Link>
        </div>
      </div>
    </header>
  );
}

function ValueProps() {
  return (
    <section className="apex-values">
      <h2 className="apex-values__title">Why APEX?</h2>
      <div className="apex-values__grid">
        <div className="apex-values__item">
          <h3>Agent-native skills</h3>
          <p>
            Built for the agentskills.io spec. Load a skill and your AI coding
            agent gains deep AWS platform-engineering knowledge — no plugins, no
            configuration.
          </p>
        </div>
        <div className="apex-values__item">
          <h3>Phased steering workflows</h3>
          <p>
            Combine skills into ordered sequences with guardrails, tool routing,
            and handoff criteria. The agent follows a structured path through
            complex multi-step tasks.
          </p>
        </div>
        <div className="apex-values__item">
          <h3>Community-driven, AWS-backed</h3>
          <p>
            Authored by AWS Solutions Architects, TAMs, and ProServe. MIT-0
            licensed. Contribute your own skills or fork and customize.
          </p>
        </div>
      </div>
    </section>
  );
}

function HowItWorks() {
  return (
    <section className="apex-steps">
      <h2 className="apex-steps__title">How it works</h2>
      <div className="apex-steps__timeline">
        <div className="apex-steps__item">
          <span className="apex-steps__number">1</span>
          <h3>Add the skill</h3>
          <p>skills:<br />&nbsp;&nbsp;- /path/to/sample-apex-skills/skills/eks-recon</p>
        </div>
        <div className="apex-steps__item">
          <span className="apex-steps__number">2</span>
          <h3>Ask your agent</h3>
          <p>The agent loads the skill context automatically when relevant.</p>
        </div>
        <div className="apex-steps__item">
          <span className="apex-steps__number">3</span>
          <h3>Ship with confidence</h3>
          <p>Platform-engineering best practices applied directly to your infrastructure.</p>
        </div>
      </div>
    </section>
  );
}

function CtaSection() {
  return (
    <section className="apex-cta-section">
      <p className="apex-cta-section__headline">Ready to explore?</p>
      <div className="apex-cta-section__actions">
        <Link className="apex-cta-section__link apex-cta-section__link--primary" to="/docs/skills">
          Browse Skills →
        </Link>
        <Link className="apex-cta-section__link apex-cta-section__link--secondary" to="/docs/steering">
          Steering Workflows →
        </Link>
      </div>
    </section>
  );
}

export default function Home(): ReactNode {
  const {siteConfig} = useDocusaurusContext();
  return (
    <Layout title={siteConfig.title} description={siteConfig.tagline}>
      <main className="landing-main">
        <HeroBanner />
        <ValueProps />
        <HowItWorks />
        <CtaSection />
      </main>
    </Layout>
  );
}
