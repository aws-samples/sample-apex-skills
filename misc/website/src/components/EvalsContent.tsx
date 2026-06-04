import type {ReactNode} from 'react';
// @ts-expect-error — JSON import resolved by webpack at build time
import evalsData from '@site/static/manifests/evals.json';

interface EvalLayer {
  raw_score: number | null;
  weight: number;
  contribution: number;
}

interface EvalSkill {
  skill: string;
  score: number;
  grade: string;
  created_at: string;
  model: string;
  git_head: string;
  pass_k_rate?: number | null;
  effective_weights?: Record<string, number>;
  layers: Record<string, EvalLayer>;
}

const skills: EvalSkill[] = evalsData as EvalSkill[];

const GRADE_COLORS: Record<string, string> = {
  A: '#10b981',
  B: '#3b82f6',
  C: '#f59e0b',
  D: '#ef4444',
  F: '#dc2626',
};

const LAYER_COLORS: Record<string, string> = {
  triggering: '#818cf8',
  process: '#34d399',
  artifact: '#fbbf24',
  knowledge: '#60a5fa',
  quality: '#f472b6',
};

const LAYER_META: {key: string; description: string}[] = [
  {key: 'triggering', description: 'Does the skill activate for the right prompts and stay silent for wrong ones?'},
  {key: 'process', description: 'Does the agent call the right tools in the right order?'},
  {key: 'artifact', description: 'Do the generated files pass terraform validate, checkov, and structural checks?'},
  {key: 'knowledge', description: 'Does the output contain expert-authored must-have content?'},
  {key: 'quality', description: 'Overall coherence and completeness (LLM grader — subjective only)'},
];

export function Methodology(): ReactNode {
  return (
    <section className="apex-eval__methodology">
      <h2 className="apex-eval__section-title">5-Layer Evaluation Architecture</h2>
      <p className="apex-eval__section-subtitle">
        Every skill is evaluated across five deterministic layers — no LLM-as-judge for correctness.
      </p>

      <div className="apex-eval__pipeline">
        {LAYER_META.map((layer, idx) => (
          <div key={layer.key} className="apex-eval__pipeline-step">
            {idx > 0 && <div className="apex-eval__pipeline-connector" />}
            <div
              className="apex-eval__pipeline-card"
              style={{'--layer-color': LAYER_COLORS[layer.key]} as React.CSSProperties}
            >
              <div className="apex-eval__pipeline-header">
                <span className="apex-eval__pipeline-number">{idx + 1}</span>
                <span className="apex-eval__pipeline-name">{layer.key}</span>
              </div>
              <p className="apex-eval__pipeline-desc">{layer.description}</p>
            </div>
          </div>
        ))}
      </div>

      <p className="apex-eval__methodology-note">
        Layers 1–4 are fully deterministic. Layer 5 is the only subjective measure.
        Weights are configurable per skill — disabled layers redistribute their weight proportionally.
      </p>
    </section>
  );
}

function ScorecardCard({skill}: {skill: EvalSkill}): ReactNode {
  const gradeColor = GRADE_COLORS[skill.grade] || '#6b7280';
  const layerKeys = ['triggering', 'process', 'artifact', 'knowledge', 'quality'];

  return (
    <div className="apex-eval__card">
      <div className="apex-eval__card-header">
        <span className="apex-eval__skill-name">{skill.skill}</span>
        <span className="apex-eval__grade" style={{backgroundColor: gradeColor}}>
          {skill.grade}
        </span>
      </div>
      <div className="apex-eval__score">
        {skill.score.toFixed(1)} / 100
      </div>
      <div className="apex-eval__layers">
        {layerKeys.map((key) => {
          const layer = skill.layers[key];
          if (!layer) return null;
          const contribution = layer.contribution;
          const barWidth = contribution > 0 ? Math.max(contribution, 0.2) : 0;
          const weight = skill.effective_weights?.[key];
          const weightLabel = weight ? `${Math.round(weight * 100)}%` : '';
          return (
            <div key={key} className="apex-eval__layer-row">
              <span className="apex-eval__layer-label">{key}</span>
              <div className="apex-eval__layer-track">
                <div
                  className="apex-eval__layer-bar"
                  style={{
                    width: barWidth > 0 ? `${barWidth}%` : '2px',
                    backgroundColor: LAYER_COLORS[key] || '#6b7280',
                    minWidth: '2px',
                  }}
                />
              </div>
              <span className="apex-eval__layer-value">
                {contribution > 0 ? contribution.toFixed(1) : '—'}
              </span>
              <span className="apex-eval__layer-weight-badge">
                {weightLabel || '—'}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export function Scorecard(): ReactNode {
  return (
    <section className="apex-eval__scorecard">
      <h2 className="apex-eval__section-title">Skill Scorecard</h2>
      <p className="apex-eval__section-subtitle">
        Live scores from the latest baseline run.
      </p>

      {skills.length === 0 ? (
        <p className="apex-eval__empty">No eval data available yet. Run the eval harness to generate scores.</p>
      ) : (
        <div className="apex-eval__grid">
          {skills.map((s) => (
            <ScorecardCard key={s.skill} skill={s} />
          ))}
        </div>
      )}
    </section>
  );
}

export const evalsStyles = `
  .apex-eval__methodology {
    margin-bottom: 4rem;
  }

  .apex-eval__section-title {
    font-size: 1.75rem;
    font-weight: 700;
    margin-bottom: 0.25rem;
  }

  .apex-eval__section-subtitle {
    color: var(--ifm-color-emphasis-600);
    margin-bottom: 2rem;
    font-size: 1.05rem;
  }

  .apex-eval__pipeline {
    display: flex;
    flex-direction: column;
    gap: 0;
    position: relative;
    padding-left: 2rem;
  }

  .apex-eval__pipeline-step {
    position: relative;
  }

  .apex-eval__pipeline-connector {
    position: absolute;
    left: -1.5rem;
    top: -0.75rem;
    width: 2px;
    height: 1.5rem;
    background: var(--ifm-color-emphasis-300);
  }

  .apex-eval__pipeline-card {
    border: 1px solid var(--ifm-color-emphasis-200);
    border-left: 4px solid var(--layer-color, #6b7280);
    border-radius: 8px;
    padding: 1rem 1.25rem;
    margin-bottom: 0.75rem;
    background: var(--ifm-background-surface-color, #fff);
    transition: box-shadow 0.15s;
  }

  .apex-eval__pipeline-card:hover {
    box-shadow: 0 2px 12px rgba(0,0,0,0.06);
  }

  .apex-eval__pipeline-header {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    margin-bottom: 0.4rem;
  }

  .apex-eval__pipeline-number {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 1.6rem;
    height: 1.6rem;
    border-radius: 50%;
    background: var(--layer-color, #6b7280);
    color: #fff;
    font-weight: 700;
    font-size: 0.85rem;
    flex-shrink: 0;
  }

  .apex-eval__pipeline-name {
    font-weight: 700;
    font-size: 1.05rem;
    text-transform: capitalize;
  }

  .apex-eval__pipeline-desc {
    margin: 0;
    color: var(--ifm-color-emphasis-700);
    font-size: 0.92rem;
    line-height: 1.5;
  }

  .apex-eval__methodology-note {
    margin-top: 1.5rem;
    padding: 0.75rem 1rem;
    background: var(--ifm-color-emphasis-100);
    border-radius: 6px;
    font-size: 0.9rem;
    color: var(--ifm-color-emphasis-700);
  }

  .apex-eval__scorecard {
    margin-bottom: 3rem;
  }

  .apex-eval__empty {
    color: var(--ifm-color-emphasis-500);
    font-style: italic;
  }

  .apex-eval__grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
    gap: 1.25rem;
  }

  .apex-eval__card {
    border: 1px solid var(--ifm-color-emphasis-200);
    border-radius: 10px;
    padding: 1.25rem;
    background: var(--ifm-background-surface-color, #fff);
    transition: box-shadow 0.15s;
  }

  .apex-eval__card:hover {
    box-shadow: 0 4px 16px rgba(0,0,0,0.07);
  }

  .apex-eval__card-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 0.5rem;
  }

  .apex-eval__skill-name {
    font-family: var(--ifm-font-family-monospace);
    font-weight: 600;
    font-size: 0.95rem;
  }

  .apex-eval__grade {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 2rem;
    height: 2rem;
    border-radius: 6px;
    color: #fff;
    font-weight: 800;
    font-size: 1.1rem;
  }

  .apex-eval__score {
    font-size: 1.4rem;
    font-weight: 700;
    margin-bottom: 1rem;
    color: var(--ifm-color-emphasis-800);
  }

  .apex-eval__layers {
    display: flex;
    flex-direction: column;
    gap: 0.4rem;
  }

  .apex-eval__layer-row {
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }

  .apex-eval__layer-weight-badge {
    width: 2.5rem;
    text-align: right;
    font-size: 0.7rem;
    font-weight: 500;
    color: var(--ifm-color-emphasis-500);
    flex-shrink: 0;
  }

  .apex-eval__layer-label {
    width: 5.5rem;
    font-size: 0.78rem;
    font-weight: 500;
    color: var(--ifm-color-emphasis-600);
    text-transform: capitalize;
    flex-shrink: 0;
  }

  .apex-eval__layer-track {
    flex: 1;
    height: 8px;
    background: var(--ifm-color-emphasis-100);
    border-radius: 4px;
    overflow: hidden;
  }

  .apex-eval__layer-bar {
    height: 100%;
    border-radius: 4px;
    transition: width 0.3s ease;
  }

  .apex-eval__layer-value {
    width: 2.5rem;
    text-align: right;
    font-size: 0.78rem;
    font-weight: 600;
    color: var(--ifm-color-emphasis-700);
    flex-shrink: 0;
  }

  @media (max-width: 768px) {
    .apex-eval__grid {
      grid-template-columns: 1fr;
    }

    .apex-eval__pipeline {
      padding-left: 1rem;
    }
  }
`;
