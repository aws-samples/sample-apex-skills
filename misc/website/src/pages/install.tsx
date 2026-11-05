import type {ReactNode} from 'react';
import Layout from '@theme/Layout';
import InstallComposer from '@site/src/components/InstallComposer';

export default function InstallPage(): ReactNode {
  return (
    <Layout
      title="Install EKS and ECS skills"
      description="Build the install command for APEX skills: pick Claude Code, Kiro CLI or Codex and the skills you want, then copy one command.">
      <main className="container margin-vert--lg">
        <h1>Install APEX Skills</h1>
        <p>
          Choose your agent and skills. The command below updates as you go.
        </p>
        <InstallComposer />
      </main>
    </Layout>
  );
}
