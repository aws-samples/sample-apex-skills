import type {ReactNode} from 'react';
import Link from '@docusaurus/Link';
import Layout from '@theme/Layout';
import skills from '@site/static/manifests/skill-finder.json';
import type {FinderSkill} from '@site/src/components/SkillFinder';
import {INSTALLER} from '@site/src/apexPin';

const allSkills = skills as FinderSkill[];

const GROUPS: {id: FinderSkill['group']; title: string; to: string}[] = [
  {id: 'eks', title: 'Amazon EKS skills', to: '/skill-finder?group=eks'},
  {id: 'ecs', title: 'Amazon ECS skills', to: '/docs/skills/ecs/'},
  {id: 'general', title: 'Router and general skills', to: '/skill-finder?group=general'},
];

function HeroBanner() {
  return (
    <header className="apex-hero">
      <div className="apex-hero__glow" />
      <div className="apex-hero__container">
        <span className="apex-hero__badge">APEX Skills · Open Source · MIT-0</span>
        <h1 className="apex-hero__title">EKS and ECS skills for AI coding agents</h1>
        <p className="apex-hero__subtitle">
          Curated AWS platform engineering skills that your coding agent loads
          when your request needs them.
        </p>
        <p className="apex-hero__meta">
          {allSkills.length} skills · agentskills.io · Claude Code · Kiro CLI · Codex
        </p>
        <div className="apex-hero__actions">
          <Link className="apex-hero__cta apex-hero__cta--primary" to="/skill-finder">
            Find a skill
          </Link>
          <Link className="apex-hero__cta apex-hero__cta--secondary" to="/install">
            Build your install command
          </Link>
        </div>
      </div>
    </header>
  );
}

// The prompt is the documented Kiro example from Getting Started; the
// router behaviour is quoted from skills/apex/SKILL.md.
function AgentDemo() {
  return (
    <section className="apex-terminal" aria-label="Example: asking your agent">
      <div className="apex-terminal__bar">
        <span className="apex-terminal__dot" />
        <span className="apex-terminal__dot" />
        <span className="apex-terminal__dot" />
        <span className="apex-terminal__label">your coding agent</span>
      </div>
      <pre className="apex-terminal__body">
        <span className="apex-terminal__prompt">&gt; </span>
        use apex to plan my EKS upgrade{'\n'}
        <span className="apex-terminal__muted">  skill loaded: apex (router){'\n'}</span>
        <span className="apex-terminal__muted">
          {'  '}infers the stage (Day 0 Design, Day 1 Build, Day 2 Operate),{'\n'}
          {'  '}then loads the skill that fits and its runbook, if any{'\n'}
        </span>
      </pre>
      <p className="apex-terminal__caption">
        Ask in your own words. In Claude Code and Kiro CLI you can also type{' '}
        <code>/apex</code>; in Codex, <code>$apex</code> (manual install from main).{' '}
        <Link to="/docs/skills/general/apex/">How the router works</Link>
      </p>
    </section>
  );
}

function ValueProps() {
  return (
    <section className="apex-values">
      <h2 className="apex-values__title">Why platform engineers use APEX Skills</h2>
      <div className="apex-values__grid">
        <div className="apex-values__item">
          <h3>Agent-native skills</h3>
          <p>
            Built for the agentskills.io spec. Load a skill and your AI coding
            agent gains deep AWS platform engineering knowledge, with no plugins
            and no configuration.
          </p>
        </div>
        <div className="apex-values__item">
          <h3>Guided runbooks</h3>
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

function SkillsByGroup() {
  return (
    <section className="apex-featured">
      <h2 className="apex-featured__title">Skills by platform</h2>
      {GROUPS.map((group) => {
        const members = allSkills.filter((s) => s.group === group.id);
        if (members.length === 0) return null;
        return (
          <div key={group.id} className="apex-group">
            <h3 className="apex-group__title">
              <Link to={group.to}>
                {group.title} ({members.length})
              </Link>
            </h3>
            <div className="apex-featured__grid">
              {members.map((s) => (
                <Link key={s.name} className="apex-featured__card" to={`${s.path}/`}>
                  <h3>{s.name}</h3>
                  <p>{s.summary}</p>
                </Link>
              ))}
            </div>
          </div>
        );
      })}
    </section>
  );
}

function HowItWorks() {
  return (
    <section className="apex-steps">
      <h2 className="apex-steps__title">How APEX Skills work with your AI coding agent</h2>
      <div className="apex-steps__timeline">
        <div className="apex-steps__item">
          <span className="apex-steps__number">1</span>
          <h3>Install</h3>
          <p>{INSTALLER}</p>
          <p>
            Pick your agent and skills in the <Link to="/install">install composer</Link>.
            For v2 and its <code>/apex</code> router, use the manual install from{' '}
            <code>main</code> (<Link to="/docs/getting-started/#manual-install">Getting Started</Link>).
          </p>
        </div>
        <div className="apex-steps__item">
          <span className="apex-steps__number">2</span>
          <h3>Ask your agent</h3>
          <p>The agent loads the skill context automatically when relevant.</p>
        </div>
        <div className="apex-steps__item">
          <span className="apex-steps__number">3</span>
          <h3>Ship with confidence</h3>
          <p>Platform engineering best practices applied directly to your infrastructure.</p>
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
        <Link className="apex-cta-section__link apex-cta-section__link--primary" to="/skill-finder">
          Find a skill →
        </Link>
        <Link className="apex-cta-section__link apex-cta-section__link--secondary" to="/docs/skills/general/apex/">
          APEX Router and Runbooks →
        </Link>
      </div>
    </section>
  );
}

export default function Home(): ReactNode {
  return (
    <Layout title="APEX Skills — AWS Platform Engineering for AI Agents" description="Curated agentic AI skills for AWS platform engineering. Open-source skills for EKS, Terraform, and infrastructure workflows, delivered through any coding agent.">
      <main className="landing-main">
        <HeroBanner />
        <AgentDemo />
        <ValueProps />
        <SkillsByGroup />
        <HowItWorks />
        <CtaSection />
      </main>
    </Layout>
  );
}
