import {useState, type ReactNode} from 'react';
import Link from '@docusaurus/Link';

// Only the routes Getting Started documents (docs/getting-started.md): the
// pinned npx installer and the manual copy from main, per agent.

const INSTALLER = 'npx apex-skills@1.3.0';
const REPO = 'https://github.com/aws-samples/sample-apex-skills.git';

type Agent = {id: string; label: string; dir: string; run: ReactNode};

const AGENTS: Agent[] = [
  {
    id: 'claude',
    label: 'Claude Code',
    dir: '~/.claude/skills',
    run: (
      <>
        Restart Claude Code. Each skill runs as <code>/&lt;skill-name&gt;</code>, such as{' '}
        <code>/eks-upgrade-check</code>. With the install from main, start with <code>/apex</code> and your task.
      </>
    ),
  },
  {
    id: 'kiro',
    label: 'Kiro CLI',
    dir: '~/.kiro/skills',
    run: (
      <>
        With the install from main, type <code>/apex</code> with your request in Kiro, or ask for it by name:
        &ldquo;use apex to plan my EKS upgrade&rdquo;. Tested on Kiro CLI 2.35.1; Kiro CLI 1.27.0 rejected{' '}
        <code>/apex</code>.
      </>
    ),
  },
];

function CopyButton({text, label}: {text: string; label: string}): ReactNode {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      className="apex-copy"
      aria-label={`Copy ${label}`}
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(text);
          setCopied(true);
          setTimeout(() => setCopied(false), 2000);
        } catch {
          setCopied(false);
        }
      }}
    >
      <span aria-live="polite">{copied ? 'Copied' : 'Copy'}</span>
    </button>
  );
}

function Command({text, label}: {text: string; label: string}): ReactNode {
  return (
    <div className="apex-command">
      <pre>
        <code>{text}</code>
      </pre>
      <CopyButton text={text} label={label} />
    </div>
  );
}

export default function InstallBlock(): ReactNode {
  const [active, setActive] = useState(AGENTS[0].id);
  const agent = AGENTS.find((a) => a.id === active) ?? AGENTS[0];
  const manual = [`git clone ${REPO}`, 'cd sample-apex-skills', `mkdir -p ${agent.dir}`, `cp -r skills/* ${agent.dir}/`].join(
    '\n',
  );

  return (
    <div className="apex-install">
      <div className="apex-install__tabs" role="group" aria-label="Agent">
        {AGENTS.map((a) => (
          <button
            key={a.id}
            type="button"
            aria-pressed={a.id === active}
            aria-controls="install-panel"
            className="apex-install__tab"
            onClick={() => setActive(a.id)}
          >
            {a.label}
          </button>
        ))}
      </div>
      <div className="apex-install__panel" id="install-panel">
        <div className="apex-install__route">
          <h3>Latest skills, with the /apex router</h3>
          <p>Copy every skill from main.</p>
          <Command text={manual} label={`manual install for ${agent.label}`} />
        </div>
        <div className="apex-install__route">
          <h3>Release 1.3.0 installer</h3>
          <p>
            Detects Claude Code and Kiro CLI and links the v1.3.0 release skills (2026-10-21): no /apex router, and
            older versions of some skills than the pages here, which describe main.
          </p>
          <Command text={INSTALLER} label="installer command" />
        </div>
        <p className="apex-install__run">{agent.run}</p>
        <p className="apex-install__more">
          Codex, AWS DevOps Agent, updates and uninstall: <Link to="/docs/getting-started">Getting started</Link>.
        </p>
      </div>
    </div>
  );
}
