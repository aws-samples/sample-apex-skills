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
      <h2 className="apex-values__title">Why Platform Engineers Use APEX Skills</h2>
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

function FeaturedSkills() {
  const skills = [
    {
      name: 'EKS Design',
      path: '/docs/skills/eks-design/',
      description:
        'Architecture design documents with Mermaid diagrams, ADRs, security architecture, and validation reports. Translates requirements into tailored EKS designs guided by Well-Architected best practices.',
    },
    {
      name: 'EKS Build',
      path: '/docs/skills/eks-build/',
      description:
        'Generate production-ready EKS Terraform projects with optional ArgoCD GitOps. Handles air-gapped networks, enterprise proxies, compliance requirements, and 29+ addon configurations.',
    },
    {
      name: 'EKS Upgrade Check',
      path: '/docs/skills/eks-upgrade-check/',
      description:
        'Automated readiness assessment across 8 categories — deprecated APIs, add-on compatibility, node health, workload risks — producing a 0–100 score with prioritized remediation.',
    },
    {
      name: 'EKS Operation Review',
      path: '/docs/skills/eks-operation-review/',
      description:
        'Structured operational excellence assessment covering 10 areas with GREEN/AMBER/RED ratings and prioritized recommendations for production clusters.',
    },
    {
      name: 'EKS Platform Engineering',
      path: '/docs/skills/eks-platform-engineering/',
      description:
        'Internal Developer Platform design — Backstage portal, ArgoCD delivery, progressive rollouts with Kargo, infrastructure abstraction, golden paths, and DORA measurement.',
    },
    {
      name: 'EKS Best Practices',
      path: '/docs/skills/eks-best-practices/',
      description:
        'Architecture and design guidance — compute strategy with Karpenter and Auto Mode, multi-tenant isolation, VPC planning, Pod Identity, upgrade strategies, and cost optimization.',
    },
    {
      name: 'EKS Reconnaissance',
      path: '/docs/skills/eks-recon/',
      description:
        'Cluster discovery and environment mapping. Detects compute strategy, IaC tooling, CI/CD pipelines, add-on inventory, networking topology, security posture, and observability automatically.',
    },
    {
      name: 'EKS MCP Server',
      path: '/docs/skills/eks-mcp-server/',
      description:
        'Live cluster operations via Model Context Protocol. List clusters, read Kubernetes resources, troubleshoot pods, deploy workloads, and check upgrade insights in real time.',
    },
  ];
  return (
    <section className="apex-featured">
      <h2 className="apex-featured__title">Featured Platform Engineering Skills</h2>
      <div className="apex-featured__grid">
        {skills.map((s) => (
          <Link key={s.name} className="apex-featured__card" to={s.path}>
            <h3>{s.name}</h3>
            <p>{s.description}</p>
          </Link>
        ))}
      </div>
    </section>
  );
}

function HowItWorks() {
  return (
    <section className="apex-steps">
      <h2 className="apex-steps__title">How APEX Skills Work with Your AI Coding Agent</h2>
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
    <Layout title="APEX Skills — AWS Platform Engineering for AI Agents" description="Curated agentic AI skills for AWS platform engineering. 12 open-source skills for EKS, Terraform, and infrastructure workflows, delivered through any coding agent.">
      <main className="landing-main">
        <HeroBanner />
        <ValueProps />
        <FeaturedSkills />
        <HowItWorks />
        <CtaSection />
      </main>
    </Layout>
  );
}
