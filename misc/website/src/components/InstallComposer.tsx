import {useEffect, useMemo, useState, type ReactNode} from 'react';
import Link from '@docusaurus/Link';
import skills from '@site/static/manifests/skill-finder.json';
import type {FinderSkill} from '@site/src/components/SkillFinder';

// Commands come only from what the repo documents: the installer flags in
// misc/installer/bin/cli.mjs (--claude-only, --kiro-only, --project,
// --no-steering) with the 1.3.0 pin from Getting Started, and the manual
// copy recipes in Getting Started (Claude Code, Kiro CLI, Codex). The
// installer installs every skill for Claude Code and Kiro CLI only, so a
// skill subset or Codex always gets the manual recipe.

const allSkills = (skills as FinderSkill[]).map((s) => s.name);

type Agent = 'claude' | 'kiro' | 'codex';

const AGENTS: {id: Agent; label: string; dir: string}[] = [
  {id: 'claude', label: 'Claude Code', dir: '~/.claude/skills'},
  {id: 'kiro', label: 'Kiro CLI', dir: '~/.kiro/skills'},
  {id: 'codex', label: 'Codex', dir: '~/.agents/skills'},
];

const INSTALLER = 'npx apex-skills@1.3.0';
const REPO = 'https://github.com/aws-samples/sample-apex-skills.git';

type Plan = {kind: 'installer' | 'manual'; command: string; why: string};

function compose(
  agents: Agent[],
  chosen: string[] | 'all',
  source: 'release' | 'main',
  project: boolean,
  steering: boolean,
): Plan | null {
  if (agents.length === 0) return null;
  if (chosen !== 'all' && chosen.length === 0) return null;
  const installerFits =
    source === 'release' && chosen === 'all' && !agents.includes('codex');
  if (installerFits) {
    const flags: string[] = [];
    if (agents.length === 1) flags.push(agents[0] === 'claude' ? '--claude-only' : '--kiro-only');
    if (project) flags.push('--project');
    if (!steering) flags.push('--no-steering');
    return {
      kind: 'installer',
      command: [INSTALLER, ...flags].join(' '),
      why: 'The installer clones the repo to ~/.apex-skills/ and links every skill into place.',
    };
  }
  const sources = chosen === 'all' ? ['skills/*'] : chosen.map((name) => `skills/${name}`);
  const lines = [`git clone ${REPO}`, 'cd sample-apex-skills', ''];
  for (const agent of AGENTS.filter((a) => agents.includes(a.id))) {
    lines.push(`mkdir -p ${agent.dir}`, `cp -r ${sources.join(' ')} ${agent.dir}/`);
  }
  const reasons: string[] = [];
  if (source === 'main') reasons.push('you chose main (v2)');
  if (chosen !== 'all') reasons.push('the installer always installs every skill');
  if (agents.includes('codex')) reasons.push('the installer does not set up Codex');
  return {
    kind: 'manual',
    command: lines.join('\n'),
    why: `Manual copy from main, because ${reasons.join(' and ')}.`,
  };
}

function CopyButton({text}: {text: string}): ReactNode {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      setCopied(false);
    }
  };
  return (
    <button type="button" className="copy-page-button" onClick={copy}>
      {copied ? 'Copied!' : 'Copy command'}
    </button>
  );
}

export default function InstallComposer(): ReactNode {
  const [agents, setAgents] = useState<Agent[]>(['claude']);
  const [chosen, setChosen] = useState<string[] | 'all'>('all');
  const [source, setSource] = useState<'release' | 'main'>('release');
  const [project, setProject] = useState(false);
  const [steering, setSteering] = useState(true);

  // Deep link from the skill finder: /install?skill=<name>.
  useEffect(() => {
    const skill = new URLSearchParams(window.location.search).get('skill');
    if (skill && allSkills.includes(skill)) setChosen([skill]);
  }, []);

  const plan = useMemo(
    () => compose(agents, chosen, source, project, steering),
    [agents, chosen, source, project, steering],
  );

  const toggleAgent = (id: Agent) =>
    setAgents((current) =>
      current.includes(id) ? current.filter((a) => a !== id) : [...current, id],
    );
  const toggleSkill = (name: string) =>
    setChosen((current) => {
      const list = current === 'all' ? [] : current;
      return list.includes(name) ? list.filter((s) => s !== name) : [...list, name];
    });

  return (
    <div className="apex-composer">
      <fieldset className="apex-finder__facet">
        <legend className="apex-finder__label">1. Your agent</legend>
        {AGENTS.map((a) => (
          <label key={a.id}>
            <input type="checkbox" checked={agents.includes(a.id)} onChange={() => toggleAgent(a.id)} />
            {a.label}
          </label>
        ))}
      </fieldset>

      <fieldset className="apex-finder__facet">
        <legend className="apex-finder__label">2. Skills</legend>
        <label>
          <input type="radio" name="apex-skills-scope" checked={chosen === 'all'} onChange={() => setChosen('all')} />
          All {allSkills.length} skills
        </label>
        <label>
          <input
            type="radio"
            name="apex-skills-scope"
            checked={chosen !== 'all'}
            onChange={() => setChosen(chosen === 'all' ? [] : chosen)}
          />
          Pick skills
        </label>
        {chosen !== 'all' && (
          <div className="apex-composer__skills">
            {allSkills.map((name) => (
              <label key={name}>
                <input type="checkbox" checked={chosen.includes(name)} onChange={() => toggleSkill(name)} />
                <code>{name}</code>
              </label>
            ))}
          </div>
        )}
      </fieldset>

      <fieldset className="apex-finder__facet">
        <legend className="apex-finder__label">3. Source</legend>
        <label>
          <input type="radio" name="apex-source" checked={source === 'release'} onChange={() => setSource('release')} />
          Latest v1 release (installer 1.3.0)
        </label>
        <label>
          <input type="radio" name="apex-source" checked={source === 'main'} onChange={() => setSource('main')} />
          <code>main</code>: v2 with the <code>/apex</code> router
        </label>
      </fieldset>

      {plan?.kind === 'installer' && (
        <fieldset className="apex-finder__facet">
          <legend className="apex-finder__label">4. Installer options</legend>
          <label>
            <input type="checkbox" checked={project} onChange={() => setProject(!project)} />
            Install to the current project instead of global (<code>--project</code>)
          </label>
          <label>
            <input type="checkbox" checked={!steering} onChange={() => setSteering(!steering)} />
            Skip steering and commands setup (<code>--no-steering</code>)
          </label>
        </fieldset>
      )}

      <div className="apex-composer__result" aria-live="polite">
        {plan ? (
          <>
            <pre className="apex-composer__command">
              <code>{plan.command}</code>
            </pre>
            <CopyButton text={plan.command} />
            <p className="apex-composer__why">{plan.why}</p>
          </>
        ) : (
          <p>Pick at least one agent and one skill.</p>
        )}
        <p className="apex-composer__why">
          Prerequisites, flags and uninstall: <Link to="/docs/getting-started/">Getting Started</Link>.
        </p>
      </div>
    </div>
  );
}
