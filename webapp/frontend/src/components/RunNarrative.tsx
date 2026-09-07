import { FeatureContributionChart } from './FeatureContributionChart'
import { fmtPct } from '../format'
import type { DetectionExplanation, MixedEvaluationResponse, ScenarioType } from '../types'

const SCENARIO_INTRO: Record<ScenarioType, string> = {
  edos:
    'This run simulates a low-volume EDoS attack: synthetic clients concentrate requests on the expensive ' +
    'report-generation endpoint, aiming to drive up replica count and cost without producing a large volume of ' +
    'traffic.',
  flash_crowd:
    'This run simulates a legitimate flash crowd: many simulated users browsing, searching and checking out — ' +
    'the arrival pattern of a genuine viral event, spread across the normal mix of endpoints.',
  mixed:
    'This run overlays a flash crowd and an EDoS attack running at the same time (scenario E3). The detector has ' +
    'to pull the attack signal out from underneath simultaneous legitimate demand.',
  interleaved:
    'This run alternates between flash-crowd and EDoS phases over time (scenario E4). The detector has to catch ' +
    'the transition as behaviour changes mid-run, not just classify the run as a whole.',
  normal:
    'This is a normal-traffic baseline run — neither class — used as a reference point for what unremarkable ' +
    'traffic looks like.',
}

export function RunNarrative({
  explanation,
  scenarioType,
  experimentId,
  mixedEvaluation,
}: {
  explanation: DetectionExplanation | null
  /** Undefined for ad-hoc simulator runs, which have no ExperimentExample
   * entry (their generated configs live outside experiments/configs/) —
   * the scenario-intro paragraph is simply omitted in that case. */
  scenarioType: ScenarioType | undefined
  experimentId: string | undefined
  mixedEvaluation: MixedEvaluationResponse | null
}) {
  if (!explanation?.available || !explanation.factors || explanation.factors.length === 0) return null

  const factors = explanation.factors
  const edosCount = factors.filter((f) => f.direction === 'closer_to_edos').length
  const fcCount = factors.filter((f) => f.direction === 'closer_to_flash_crowd').length

  const scenario = scenarioType
  const evalEntry =
    mixedEvaluation?.available && experimentId ? mixedEvaluation.results[experimentId] : undefined

  return (
    <div className="card" style={{ marginBottom: 14, lineHeight: 1.65, fontSize: 13 }}>
      <h4 style={{ marginBottom: 8 }}>Why This Run Was Classified This Way</h4>
      {scenario && <p style={{ marginBottom: 12 }}>{SCENARIO_INTRO[scenario]}</p>}
      <FeatureContributionChart explanation={explanation} />
      <p style={{ marginTop: 12 }}>
        Across all {factors.length} tracked features for this run, {edosCount} point toward EDoS and {fcCount}{' '}
        point toward flash-crowd — the longer bars above carry the most weight (highest SHAP importance) in that
        split. Hover a bar for this run's actual value against both class averages.
      </p>
      {evalEntry && (
        <p>
          Across the {evalEntry.cascade_lightgbm.n_windows} feature window
          {evalEntry.cascade_lightgbm.n_windows === 1 ? '' : 's'} extracted from this specific run, CASCADE recalled{' '}
          {fmtPct(evalEntry.cascade_lightgbm.recall)} of EDoS windows while flagging{' '}
          {fmtPct(evalEntry.cascade_lightgbm.flash_crowd_false_positive_rate)} of flash-crowd windows as EDoS —
          this is the closest measurement of how well it tracked the phase changes within this run, rather than
          the run as a single label.
        </p>
      )}
    </div>
  )
}
