import { apiFetch } from '../../services/apiBase'
import { useCallback, useEffect, useState } from 'react';

import type { ProofBoardPayload } from './evidence';

export interface LabEvidenceState {
  data: ProofBoardPayload | null;
  error: string | null;
  loading: boolean;
  reload: () => void;
}

export function useLabEvidence(): LabEvidenceState {
  const [data, setData] = useState<ProofBoardPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [requestVersion, setRequestVersion] = useState(0);

  const reload = useCallback(() => {
    setRequestVersion((version) => version + 1);
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    let active = true;

    setLoading(true);
    setError(null);

    void apiFetch('/api/observatory/proof-board', {
      credentials: 'include',
      signal: controller.signal,
    })
      .then(async (response) => {
        if (!response.ok) {
          throw new Error(`Proof-board request failed with HTTP ${response.status}`);
        }
        return (await response.json()) as ProofBoardPayload;
      })
      .then((payload) => {
        if (!active) return;
        setData(payload);
        setLoading(false);
      })
      .catch((reason: unknown) => {
        if (!active || controller.signal.aborted) return;
        setData(null);
        setError(
          reason instanceof Error
            ? reason.message
            : 'The proof-board response is unavailable.',
        );
        setLoading(false);
      });

    return () => {
      active = false;
      controller.abort();
    };
  }, [requestVersion]);

  return { data, error, loading, reload };
}
