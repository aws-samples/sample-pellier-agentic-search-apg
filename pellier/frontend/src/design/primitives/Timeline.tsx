import React from 'react';
import { Check, Minus } from 'lucide-react';
import { colors } from '../tokens';

export interface TimelineStep {
  number: number;
  label: string;
  status: 'pending' | 'in-progress' | 'complete' | 'skipped';
  tag?: string;
  timestamp?: string;
  content?: React.ReactNode;
}

export interface TimelineProps {
  steps: TimelineStep[];
}

/**
 * Timeline primitive — vertical numbered steps with connecting lines.
 *
 * Pending: muted (inkQuiet color, dashed connecting line).
 * In-progress: pulsing circle (terracotta), solid connecting line, animate-pulse.
 * Complete: filled circle (espresso), solid connecting line, checkmark inside.
 * Skipped: dimmed circle with skip indicator (dash), dashed connecting line, reduced opacity.
 * Respects prefers-reduced-motion for pulsing animation.
 */
export const Timeline: React.FC<TimelineProps> = ({ steps }) => {
  return (
    <div className="flex flex-col" role="list" aria-label="Timeline">
      {steps.map((step, index) => {
        const isLast = index === steps.length - 1;

        return (
          <div key={step.number} className="flex gap-4" role="listitem">
            {/* Left column: circle + connecting line */}
            <div className="flex flex-col items-center">
              <StepCircle status={step.status} number={step.number} />
              {!isLast && <ConnectingLine status={step.status} nextStatus={steps[index + 1]?.status} />}
            </div>

            {/* Right column: label, tag, timestamp, content */}
            <div className={['flex-1 pb-6', step.status === 'skipped' ? 'opacity-50' : ''].join(' ')}>
              <div className="flex items-center gap-2 min-h-[32px]">
                <span
                  className={[
                    'text-sm font-sans font-medium',
                    step.status === 'pending' || step.status === 'skipped'
                      ? 'text-ink-quiet'
                      : 'text-espresso',
                  ].join(' ')}
                >
                  {step.label}
                </span>
                {step.tag && (
                  <span className="inline-flex items-center rounded-full bg-sand px-2 py-0.5 text-xs font-sans font-medium uppercase tracking-wider text-espresso">
                    {step.tag}
                  </span>
                )}
              </div>
              {step.timestamp && (
                <p className="text-microcopy mt-0.5">{step.timestamp}</p>
              )}
              {step.content && <div className="mt-2">{step.content}</div>}
            </div>
          </div>
        );
      })}
    </div>
  );
};

/** Step circle indicator */
const StepCircle: React.FC<{ status: TimelineStep['status']; number: number }> = ({
  status,
  number,
}) => {
  const base =
    'w-8 h-8 rounded-full flex items-center justify-center text-xs font-sans font-medium shrink-0';

  switch (status) {
    case 'complete':
      return (
        <div className={`${base} bg-espresso text-cream-50`}>
          <Check size={14} strokeWidth={2.5} />
        </div>
      );
    case 'in-progress':
      return (
        <div className={`${base} bg-accent text-cream-50 motion-safe:animate-pulse`}>
          {number}
        </div>
      );
    case 'skipped':
      return (
        <div className={`${base} bg-sand/60 text-ink-quiet`}>
          <Minus size={14} strokeWidth={2.5} />
        </div>
      );
    case 'pending':
    default:
      return (
        <div className={`${base} border-2 border-sand text-ink-quiet`}>
          {number}
        </div>
      );
  }
};

/** Connecting line between steps */
const ConnectingLine: React.FC<{
  status: TimelineStep['status'];
  nextStatus?: TimelineStep['status'];
}> = ({ status, nextStatus }) => {
  // Dashed if current step is pending or skipped, or next step is pending/skipped
  const isDashed =
    status === 'pending' ||
    status === 'skipped' ||
    nextStatus === 'pending' ||
    nextStatus === 'skipped';

  return (
    <div
      className={[
        'w-0.5 flex-1 min-h-[24px]',
        isDashed ? 'border-l-2 border-dashed border-sand' : 'bg-espresso/20',
      ].join(' ')}
      aria-hidden="true"
    />
  );
};

void colors;

export default Timeline;
