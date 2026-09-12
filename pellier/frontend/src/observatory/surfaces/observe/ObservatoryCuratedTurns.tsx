/**
 * Guided requests are durable Aurora workshop_scenarios rows. They are not
 * browser fixtures: when the data plane is unavailable, the Workbench says so
 * instead of presenting a convincing but disconnected list.
 */

import { useEffect, useState } from 'react';
import { AlertCircle, Loader2, Play, Wrench } from 'lucide-react';
import { Link } from 'react-router-dom';
import ResponsiveImage from '../../../components/ResponsiveImage';
import {
  WORKSHOP_TURN_STAGES,
  WORKSHOP_EVIDENCE_GUIDANCE,
  type WorkshopJourney,
} from '../../../data/workshopJourneys';

interface LiveScenario {
  id: number;
  ordinal: number;
  prompt: string;
  journeyRole?: 'required' | 'explore';
  journeyStage?: 'establish' | 'exercise' | 'prove' | null;
  productName: string | null;
  imageUrl: string | null;
}

export interface ObservatoryCuratedTurnsProps {
  journey: WorkshopJourney;
  running: boolean;
  activeIndex: number | null;
  onInspect: (query: string, index: number) => void;
  ready?: boolean;
  /**
   * Whether the request at this index may run yet. The three-turn journey is
   * a conversation, so turn N waits for turn N-1; a turn offered out of order
   * would be answered by an agent that never saw the turns it refers to.
   * Explore prompts are side excursions and the predicate exempts them.
   *
   * Pass the same function the run itself is gated on. This decides whether
   * the button is pressable, so a looser answer here is a dead click.
   */
  canRunTurn?: (index: number) => boolean;
  anchorError?: string | null;
  id?: string;
}

export default function ObservatoryCuratedTurns({
  journey,
  running,
  activeIndex,
  onInspect,
  ready = true,
  canRunTurn = () => true,
  anchorError = null,
  id = 'curated-turns',
}: ObservatoryCuratedTurnsProps) {
  const [scenarios, setScenarios] = useState<LiveScenario[]>([]);
  const [loading, setLoading] = useState(true);
  const [retryVersion, setRetryVersion] = useState(0);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    setScenarios([]);
    if (journey.surface === 'operator') {
      setScenarios(
        journey.prompts.map((prompt, index) => ({
          id: index + 1,
          ordinal: index + 1,
          prompt,
          journeyRole: 'required',
          journeyStage: (['establish', 'exercise', 'prove'] as const)[index],
          productName: null,
          imageUrl: null,
        })),
      );
      setLoading(false);
      return () => {
        cancelled = true;
      };
    }

    void fetch(
      `/api/observatory/scenarios?persona=${encodeURIComponent(journey.anchorId)}`,
    )
      .then(async (response) => {
        if (!response.ok) {
          throw new Error('Guided requests are temporarily unavailable. You can reload them here.');
        }
        return response.json() as Promise<{ scenarios?: LiveScenario[] }>;
      })
      .then((payload) => {
        if (!cancelled) setScenarios(payload.scenarios ?? []);
      })
      .catch((reason: unknown) => {
        if (!cancelled) {
          setError(
            reason instanceof Error
              ? reason.message
              : 'Live scenarios are unavailable.',
          );
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [journey, retryVersion]);

  const guidance = WORKSHOP_EVIDENCE_GUIDANCE[journey.anchorId];

  const requiredScenarios = scenarios.filter((scenario) =>
    scenario.journeyRole
      ? scenario.journeyRole === 'required'
      : scenario.ordinal <= 3,
  );
  const exploreScenarios = scenarios.filter((scenario) =>
    scenario.journeyRole
      ? scenario.journeyRole === 'explore'
      : scenario.ordinal > 3,
  );

  const renderScenario = (scenario: LiveScenario, index: number) => {
    const isActive = activeIndex === index;
    // One predicate decides both the button and the run. The explore
    // exemption lives inside it, not here, so an offered prompt always runs.
    const waitingOnEarlierTurn = !canRunTurn(index);
    const stage = WORKSHOP_TURN_STAGES[Math.min(scenario.ordinal - 1, 2)];
    const isBuildCheckpoint =
      journey.surface !== 'operator' &&
      scenario.journeyStage === 'prove' &&
      !scenario.imageUrl;
    const content = (
      <>
        <span className="labs-turn-media" aria-hidden="true">
          {scenario.imageUrl ? (
            <ResponsiveImage
              src={scenario.imageUrl}
              alt=""
              loading="lazy"
              decoding="async"
              sizes="74px"
            />
          ) : isBuildCheckpoint ? (
            <span className="labs-turn-build-checkpoint">
              <Wrench size={20} strokeWidth={1.6} />
              <span>Build</span>
            </span>
          ) : (
            <span>{journey.surface === 'operator' ? 'Operator case' : 'No catalog image'}</span>
          )}
        </span>
        <span className="labs-turn-copy">
          <span className="labs-turn-stage">
            {scenario.journeyRole === 'explore'
              ? `Explore ${scenario.ordinal - 3}`
              : `Turn ${scenario.ordinal} · ${stage}`}
            {waitingOnEarlierTurn ? (
              <em className="labs-turn-waiting">
                {`after turn ${scenario.ordinal - 1}`}
              </em>
            ) : null}
          </span>
          <strong>{scenario.prompt}</strong>
          <small>
            {journey.surface === 'operator'
              ? 'Authenticated staff investigation'
              : isBuildCheckpoint
                ? 'Build checkpoint · inventory proof'
              : scenario.productName
                ? `Catalog preview · ${scenario.productName}`
                : 'Aurora scenario'}
          </small>
        </span>
      </>
    );

    if (journey.surface === 'operator') {
      return (
        <article className="labs-turn labs-turn-static">
          {content}
        </article>
      );
    }

    return (
      <button
        type="button"
        className="labs-turn"
        data-active={isActive ? 'true' : undefined}
        data-running={isActive && running ? 'true' : undefined}
        data-waiting={waitingOnEarlierTurn ? 'true' : undefined}
        disabled={running || !ready || waitingOnEarlierTurn}
        aria-label={`Inspect: ${scenario.prompt}`}
        onClick={() => onInspect(scenario.prompt, index)}
      >
        {content}
        <span className="labs-turn-action" aria-hidden="true">
          {isActive && running ? (
            <Loader2 className="spin" size={15} />
          ) : (
            <Play size={14} fill="currentColor" />
          )}
        </span>
      </button>
    );
  };

  return (
    <section className="labs-turns" id={id} aria-labelledby="labs-turns-title">
      <header className="labs-turns-heading">
        <h2 id="labs-turns-title">
          {journey.surface === 'operator' ? 'Operator close' : 'Shopper turns'}
        </h2>
        <p>
          {journey.surface === 'operator'
            ? `Jessica's governed case continues in the separately authenticated staff surface.`
            : `Aurora-backed guided requests for ${journey.anchorName}`}
        </p>
      </header>

      {!loading && !error && journey.surface === 'operator' ? (
        <Link
          className="labs-turns-operator-link"
          to="/operator/clients/CUST-JESSICA?guided=service-recovery#operator-concierge-title"
        >
          <span>
            <strong>Open Jessica in Operator</strong>
            <small>Continue with the separately authenticated staff desk.</small>
          </span>
        </Link>
      ) : null}

      {loading ? (
        <div className="labs-turns-skeleton" role="status" aria-label="Loading guided requests">
          {[0, 1, 2].map((index) => (
            <span key={index} className="labs-turn-skeleton-row" aria-hidden="true" />
          ))}
        </div>
      ) : null}
      {error ? (
        <div className="labs-turns-state" role="alert">
          <AlertCircle size={16} aria-hidden="true" />
          <span>{error}</span>
          <button type="button" className="pellier-retry" onClick={() => setRetryVersion(v => v + 1)}>Reload requests</button>
        </div>
      ) : null}
      {!loading && !error && !ready && anchorError ? (
        <div
          className="labs-turns-state"
          role="alert"
        >
          {`Unable to open ${journey.anchorName}'s guided session: ${anchorError}`}
        </div>
      ) : null}
      {!loading && !error && ready && scenarios.length === 0 ? (
        <div className="labs-turns-state">
          Aurora has no guided requests for this profile yet.
        </div>
      ) : null}

      {!loading && !error && requiredScenarios.length > 0 ? (
        <section
          className="labs-turns-group"
          aria-label="Required three-turn journey"
        >
          <div className="labs-turns-group-heading labs-turns-group-heading-context">
            <h3>Required three-turn journey</h3>
            <span className="labs-turns-context">
              Each turn keeps the previous conversation.
            </span>
          </div>
          <ol className="labs-turns-list" data-journey-role="required">
            {requiredScenarios.map((scenario, index) => (
              <li key={scenario.id}>{renderScenario(scenario, index)}</li>
            ))}
          </ol>
        </section>
      ) : null}

      <details className="labs-evidence-guidance">
        <summary>Prediction, proof &amp; optional challenge</summary>
        <dl>
          <div><dt>Predict before running</dt><dd>{guidance.prediction}</dd></div>
          <div><dt>Inspect the evidence</dt><dd>{guidance.evidence}</dd></div>
          <div><dt>Change one thing</dt><dd>{guidance.challenge}<p>{guidance.inspect}</p></dd></div>
        </dl>
        {journey.anchorId === 'anna' ? <p className="labs-benchmark-note">The natural conversation and the retrieval benchmark serve different purposes. Compare metrics using the fixed benchmark query: “A housewarming gift under $100 that is currently in stock.” Keep its labels unchanged.</p> : null}
      </details>

      {!loading && !error && exploreScenarios.length > 0 ? (
        <section className="labs-turns-group" aria-label="Explore further">
          <div className="labs-turns-group-heading">
            <h3>Explore further</h3>
            <span>Optional extensions</span>
          </div>
          <ol className="labs-turns-list labs-turns-list-explore" data-journey-role="explore">
            {exploreScenarios.map((scenario, index) => (
              <li key={scenario.id}>
                {renderScenario(scenario, requiredScenarios.length + index)}
              </li>
            ))}
          </ol>
        </section>
      ) : null}

    </section>
  );
}
