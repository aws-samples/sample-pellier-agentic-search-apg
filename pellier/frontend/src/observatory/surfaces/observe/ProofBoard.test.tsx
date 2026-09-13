import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import ProofBoard from './ProofBoard';

const proofBoardPayload = {
  status: 'ready',
  readiness: {
    status: 'ready',
    checks: [
      {
        id: 'aurora',
        label: 'Aurora PostgreSQL',
        state: 'pass',
        detail: 'Catalog 1,000 products, warehouse 180 rows, audit ledger 7 rows.',
        required: true,
      },
      {
        id: 'gateway',
        label: 'AgentCore Gateway',
        state: 'pass',
        detail: 'Gateway URL configured.',
        required: true,
      },
    ],
  },
  managedReceipt: {
    present: true,
    traceKind: 'managed-runtime-receipt',
    runtime: 'agentcore-managed',
    rail: 'gateway-mcp',
    jwtPassthrough: true,
    gatewayPassthrough: true,
    traceId: '4bf92f3577b34da6a3ce929d0e0e4736',
    runtimeRequestId: 'request-123',
    sessionId: 'managed-proof',
    evidenceProvenance: 'agentcore-service-telemetry',
    managedTrace: {
      traceId: '4bf92f3577b34da6a3ce929d0e0e4736',
      runtimeRequestId: 'request-123',
      sessionId: 'managed-proof',
      xrayConsoleUrl: 'https://console.example/xray',
      logsConsoleUrl: 'https://console.example/logs',
    },
    governedReceiptPresent: true,
    latestGovernedReceiptId: 505,
    governedPrincipalId: 'CUST-MARCO',
    governedPrincipalLabel: 'Marco (Cognito JWT)',
    governedVerifiedSubject: 'cognito-sub-marco',
    governedVerifiedUsername: 'marco@example.com',
    governedIdentitySource: 'cognito_access_token',
    governedTokenFingerprint: 'abc123def456abc123def456abc123def456abc123def456abc123def456abcd',
    governedDecision: 'ALLOW',
    governedTool: 'initiate_return',
    governedArgs: { customer_id: 'theo', product_id: '37', reason: 'damaged' },
    gatewayAuditPresent: true,
    latestGatewayAuditId: 303,
    writeOperationPresent: true,
    writeOperationKey: 'operator-review:8:aaaaaaaa',
    writeOperationName: 'initiate_return',
    writeOperationCompletedAt: '2026-08-29T12:00:00Z',
  },
  cards: [
    {
      id: 'marco-floor-check',
      lab: 'Lab 1: Build a PostgreSQL-Grounded Agent',
      group: 'Agent and tool evidence',
      title: 'Wire Marco to check_inventory',
      status: 'complete',
      required: true,
      surface: 'Code Editor + Pellier',
      summary: "The Inventory Agent tool is wired and Marco's warehouse turn leaves a check_inventory audit row.",
      evidence: ['Latest check_inventory row: audit_id 101'],
      fallback: {
        label: 'PostgreSQL proof',
        command: 'psql -X -v ON_ERROR_STOP=1 -c "SELECT * FROM pellier.tool_audit"',
      },
      links: [{ label: 'Tools', to: '/observatory/tools' }],
    },
    {
      id: 'retrieval-comparison',
      lab: 'Lab 2: Build and Measure PostgreSQL Hybrid Retrieval',
      group: 'Retrieval evidence',
      title: 'Compare retrieval strategies',
      status: 'available',
      required: true,
      surface: 'Pellier Observatory',
      summary: 'The retrieval comparison keeps source and ranking evidence visible.',
      evidenceSource: 'Aurora search strategy comparison',
      evidence: ['Hybrid retrieval preserves candidate provenance.'],
      fallback: {
        label: 'PostgreSQL proof',
        command: 'psql -X -v ON_ERROR_STOP=1 -c "SELECT * FROM pellier.retrieval_receipts"',
      },
      links: [{ label: 'Retrieval comparison', to: '/observatory/performance' }],
    },
    {
      id: 'audit-ledger',
      lab: 'Lab 3: Deploy and Operate Agents with Amazon Bedrock AgentCore',
      title: 'Prove the audit trail in Aurora',
      status: 'complete',
      required: true,
      surface: 'Aurora PostgreSQL',
      summary: 'The live tool_audit ledger contains the expected identity, tool, and outcome.',
      evidence: ['Latest audit row: audit_id 303'],
      fallback: {
        label: 'SQL fallback',
        command: 'SELECT audit_id, caller, tool_name FROM pellier.tool_audit ORDER BY audit_id DESC;',
      },
      links: [{ label: 'Sessions', to: '/observatory/sessions' }],
    },
    {
      id: 'managed-rail',
      lab: 'Lab 3: Deploy and Operate Agents with Amazon Bedrock AgentCore',
      group: 'Managed boundaries',
      title: 'Prove the managed Runtime and Gateway rail',
      status: 'complete',
      required: true,
      surface: 'Runtime receipt',
      summary: 'After a managed Runtime turn, the receipt shows passthrough.',
      evidence: [
        'AgentCore Memory configured for authenticated session history',
        'JWT passthrough: true',
      ],
      fallback: {
        label: 'AgentCore Runtime proof',
        command: 'npx -y @aws/agentcore@0.29.0 invoke --runtime pellier_orchestrator',
      },
      links: [{ label: 'Sessions', to: '/observatory/sessions' }],
    },
    {
      id: 'runtime-gateway-policy',
      lab: 'Lab 4: Build Governed Agent Actions with Cedar',
      group: 'Governance evidence',
      title: 'Verify Gateway, Cedar, and the governed receipt',
      status: 'complete',
      required: true,
      surface: 'Gateway policy receipt',
      summary: 'The Gateway decision and the corresponding audit row are correlated.',
      evidence: ['ALLOW receipt linked to tool_audit 303.'],
      fallback: {
        label: 'AgentCore validation',
        command: 'npx -y @aws/agentcore@0.29.0 validate --json',
      },
      links: [{ label: 'Gateway & Policy', to: '/observatory/write-path' }],
    },
  ],
};

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

describe('ProofBoard', () => {
  it('renders a distinct Cognito state when principal-scoped proof is unauthenticated', async () => {
    vi.stubEnv('VITE_COGNITO_DOMAIN', 'auth.example.com');
    vi.stubEnv('VITE_COGNITO_CLIENT_ID', 'client-1');
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        new Response(JSON.stringify({ detail: 'authentication_required' }), {
          status: 401,
          headers: { 'Content-Type': 'application/json' },
        }),
      ),
    );

    render(
      <MemoryRouter>
        <ProofBoard />
      </MemoryRouter>,
    );

    expect(
      await screen.findByRole('heading', { name: 'Cognito identity required' }),
    ).toBeInTheDocument();
    expect(screen.getByRole('alert')).toHaveTextContent(
      'Proof Board evidence is scoped to the verified caller.',
    );
    expect(
      screen.getByRole('link', { name: 'Authenticate with Cognito' }),
    ).toHaveAttribute('href', '/api/auth/signin?provider=email');
    expect(
      screen.queryByText(/Proof board API unavailable/),
    ).not.toBeInTheDocument();
  });

  it('keeps non-authentication failures in the API unavailable state', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        new Response(JSON.stringify({ detail: 'service_unavailable' }), {
          status: 503,
          headers: { 'Content-Type': 'application/json' },
        }),
      ),
    );

    render(
      <MemoryRouter>
        <ProofBoard />
      </MemoryRouter>,
    );

    expect(
      await screen.findByText('Proof board API unavailable: HTTP 503'),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole('heading', { name: 'Cognito identity required' }),
    ).not.toBeInTheDocument();
  });

  it('renders readiness checks, managed receipt, and proof card fallbacks', async () => {
    const fetchMock = vi.fn(async () =>
      new Response(JSON.stringify(proofBoardPayload), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    );
    vi.stubGlobal('fetch', fetchMock);

    render(
      <MemoryRouter>
        <ProofBoard />
      </MemoryRouter>,
    );

    expect(await screen.findByText('Proof Board')).toBeInTheDocument();
    expect(
      screen.getByText(
        'Read the durable runtime, policy, execution, and Aurora evidence recorded by the workshop. Run the SQL yourself when you need the proof rather than a summary.',
      ),
    ).toBeInTheDocument();
    expect(
      screen.queryByTestId('observatory-particle-canvas'),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByText('Run a live agent turn and inspect the evidence it emits.'),
    ).not.toBeInTheDocument();
    expect(screen.getByTestId('governed-proof-rail')).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith('/api/observatory/proof-board', {
      credentials: 'include',
    });
    await waitFor(() => {
      expect(
        screen.getByRole('heading', { name: 'Aurora PostgreSQL' }),
      ).toBeInTheDocument();
    });
    expect(screen.getByText('AgentCore Gateway')).toBeInTheDocument();
    expect(screen.getByText('gateway-mcp')).toBeInTheDocument();
    expect(
      screen.getAllByText('marco@example.com via cognito_access_token').length,
    ).toBeGreaterThan(0);
    expect(screen.getByText(/sha256 abc123def456\.\.\. · subject cognito-sub-marco/)).toBeInTheDocument();
    expect(screen.getAllByText('ALLOW').length).toBeGreaterThan(0);
    expect(screen.getByTestId('governance-receipt-policy')).toHaveTextContent(
      'Was the action permitted?',
    );
    expect(screen.getByTestId('governance-receipt-execution')).toHaveTextContent(
      'What actually ran?',
    );
    expect(screen.getByTestId('managed-trace-correlation')).toHaveTextContent(
      '4bf92f3577b34da6a3ce929d0e0e4736',
    );
    expect(screen.getByTestId('managed-trace-correlation')).toHaveTextContent(
      'request-123',
    );
    expect(screen.getByRole('link', { name: 'Trace in CloudWatch' })).toHaveAttribute(
      'href',
      'https://console.example/xray',
    );
    expect(screen.getByRole('link', { name: 'Runtime logs' })).toHaveAttribute(
      'href',
      'https://console.example/logs',
    );
    expect(screen.getByTestId('governance-receipt-data')).toHaveTextContent(
      'What reached the system of record?',
    );
    expect(screen.getByTestId('governance-receipt-data')).toHaveTextContent(
      'write_operations',
    );
    expect(screen.getByTestId('governance-receipt-data')).toHaveTextContent(
      'operator-review:8:aaaaaaaa',
    );
    expect(screen.getByTestId('proof-card-marco-floor-check')).toHaveTextContent(
      'Wire Marco to check_inventory',
    );
    expect(
      screen.getAllByText('Lab 1: Build a PostgreSQL-Grounded Agent'),
    ).toHaveLength(2);
    expect(
      screen.getAllByText(
        'Lab 3: Deploy and Operate Agents with Amazon Bedrock AgentCore',
      ).length,
    ).toBeGreaterThan(0);
    expect(screen.queryByText(/^Act (I|II|III)$/)).not.toBeInTheDocument();
    expect(
      screen.getByText(
        'npx -y @aws/agentcore@0.29.0 invoke --runtime pellier_orchestrator',
      ),
    ).toBeInTheDocument();
  });

  // Lab 3's whole claim is "Runtime executed the revision I packaged". The
  // invoke response carries no version, so these three states are the only
  // thing separating a real proof from a green invocation of stale code.
  describe('executed revision', () => {
    const renderWithReceipt = async (
      receipt: Record<string, unknown>,
    ): Promise<void> => {
      const payload = {
        ...proofBoardPayload,
        managedReceipt: { ...proofBoardPayload.managedReceipt, ...receipt },
      };
      vi.stubGlobal(
        'fetch',
        vi.fn(
          async () =>
            new Response(JSON.stringify(payload), {
              status: 200,
              headers: { 'Content-Type': 'application/json' },
            }),
        ),
      );
      render(
        <MemoryRouter>
          <ProofBoard />
        </MemoryRouter>,
      );
      expect(await screen.findByText('Proof Board')).toBeInTheDocument();
    };

    it('reports the deployed package as this checkout when the digests match', async () => {
      await renderWithReceipt({
        buildFingerprint: 'abc123def456aaaa',
        localBuildFingerprint: 'abc123def456aaaa',
        buildState: 'current',
      });
      const row = await screen.findByTestId('managed-build-fingerprint');
      expect(row).toHaveAttribute('data-build-state', 'current');
      expect(row).toHaveTextContent('This checkout');
      // A match still prints both sides. The badge is a conclusion; the two
      // digests are what it was read from, and a participant asked to trust
      // the badge alone cannot check the claim the lab is making.
      expect(row).toHaveTextContent('executed abc123def456');
      expect(row).toHaveTextContent('expected abc123def456');
    });

    it('names both digests when the deployment is older than this checkout', async () => {
      await renderWithReceipt({
        buildFingerprint: 'aaaaaaaaaaaa1111',
        localBuildFingerprint: 'bbbbbbbbbbbb2222',
        buildState: 'stale',
      });
      const row = await screen.findByTestId('managed-build-fingerprint');
      expect(row).toHaveAttribute('data-build-state', 'stale');
      expect(row).toHaveTextContent('Older deployment');
      // Both sides are shown: "yours differs" is only actionable if the
      // participant can see which two things differ.
      expect(row).toHaveTextContent('executed aaaaaaaaaaaa');
      expect(row).toHaveTextContent('expected bbbbbbbbbbbb');
    });

    it('reports an unstamped runtime as not reported, never as stale', async () => {
      // A runtime deployed before the fingerprint existed cannot report one.
      // Rendering that as a mismatch would send a participant hunting a
      // deployment fault that is not there.
      await renderWithReceipt({
        buildFingerprint: '',
        localBuildFingerprint: 'bbbbbbbbbbbb2222',
        buildState: 'unknown',
      });
      const row = await screen.findByTestId('managed-build-fingerprint');
      expect(row).toHaveAttribute('data-build-state', 'unknown');
      expect(row).toHaveTextContent('Not reported');
      expect(row).toHaveTextContent('executed not reported');
      expect(row).toHaveTextContent('expected bbbbbbbbbbbb');
      expect(row).not.toHaveTextContent('Older deployment');
    });

    it('treats a receipt with no build fields at all as unknown', async () => {
      // Older backends do not send these keys; the surface must not read
      // `undefined` as a mismatch.
      await renderWithReceipt({
        buildFingerprint: undefined,
        localBuildFingerprint: undefined,
        buildState: undefined,
      });
      const row = await screen.findByTestId('managed-build-fingerprint');
      expect(row).toHaveAttribute('data-build-state', 'unknown');
      expect(row).toHaveTextContent('Not reported');
    });
  });

  it('keeps the governed path compact until a participant selects a stage', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        new Response(JSON.stringify(proofBoardPayload), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
      ),
    );

    render(
      <MemoryRouter>
        <ProofBoard />
      </MemoryRouter>,
    );

    expect(await screen.findByRole('tab', { name: /Ground answers/i })).toHaveAttribute(
      'aria-selected',
      'true',
    );
    fireEvent.click(screen.getByRole('tab', { name: /Runtime & memory/i }));
    expect(screen.getByRole('tabpanel')).toHaveTextContent(
      'AgentCore Memory configured for authenticated session history',
    );
    expect(screen.getByRole('tabpanel')).toHaveTextContent('Memory and managed receipt');

    fireEvent.click(screen.getByRole('tab', { name: /Policy & receipt/i }));

    expect(screen.getByRole('tab', { name: /Policy & receipt/i })).toHaveAttribute(
      'aria-selected',
      'true',
    );
    expect(screen.getByRole('tabpanel')).toHaveTextContent(
      'Was the action allowed, stopped, or recorded with evidence?',
    );
    expect(screen.getByRole('tabpanel')).toHaveTextContent('ALLOW · tool_audit 303');
    expect(screen.getByRole('link', { name: 'Open checkpoint' }))
      .toHaveAttribute('href', '#runtime-gateway-policy');
  });

  it('fails closed when a proof-board response is missing a required checkpoint', async () => {
    const cards = proofBoardPayload.cards.filter((card) => card.id !== 'retrieval-comparison');
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        new Response(JSON.stringify({ ...proofBoardPayload, cards }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
      ),
    );

    render(
      <MemoryRouter>
        <ProofBoard />
      </MemoryRouter>,
    );

    await screen.findByTestId('governed-proof-rail');
    fireEvent.click(screen.getByRole('tab', { name: /Retrieval/i }));

    const panel = screen.getByRole('tabpanel');
    expect(panel).toHaveTextContent('Evidence unavailable');
    expect(panel).toHaveTextContent(
      'This Proof Board response does not include the checkpoint required for this stage.',
    );
    expect(panel.querySelector('a')).toBeNull();
  });

  it('renders Gateway/Cedar DENY as a verified no-row proof', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        new Response(JSON.stringify({
          ...proofBoardPayload,
          managedReceipt: {
            ...proofBoardPayload.managedReceipt,
            governedDecision: 'DENY',
            governedPolicyName: 'workshop_identity_match_forbid',
            gatewayAuditPresent: false,
            gatewayAuditAbsenceVerified: true,
            latestGatewayAuditId: null,
            writeOperationPresent: false,
            writeOperationKey: '',
            writeOperationName: '',
            writeOperationCompletedAt: null,
            absenceCheckDetail: 'Gateway/Cedar DENY: governed receipt has no audit_id and no tool_audit row was written.',
          },
        }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
      ),
    );

    render(
      <MemoryRouter>
        <ProofBoard />
      </MemoryRouter>,
    );

    expect(
      (await screen.findAllByText(/DENY via workshop_identity_match_forbid/)).length,
    ).toBeGreaterThan(0);
    expect(screen.getByTestId('governance-receipt-policy')).toHaveTextContent('DENY');
    expect(screen.getByTestId('governance-receipt-execution')).toHaveTextContent(
      'stopped before target execution',
    );
    expect(screen.getByTestId('governance-receipt-data')).toHaveTextContent(
      'No system-of-record write was attempted',
    );
    expect(screen.getByText('Cedar DENY: tool target did not execute')).toBeInTheDocument();
    expect(screen.getByText('Gateway/Cedar DENY left no tool_audit row')).toBeInTheDocument();
    expect(screen.getByText(/No-row DENY is scoped to the Gateway\/Cedar rail/)).toBeInTheDocument();
  });

  it('maps card ids to labs while an older local backend is still running', async () => {
    const cards = proofBoardPayload.cards.map(({ lab: _lab, ...card }) => card);
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        new Response(JSON.stringify({ ...proofBoardPayload, cards }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
      ),
    );

    render(
      <MemoryRouter>
        <ProofBoard />
      </MemoryRouter>,
    );

    // Four-lab spine: managed execution and audit share Lab 3.
    expect(
      await screen.findAllByText('Lab 1: Build a PostgreSQL-Grounded Agent'),
    ).toHaveLength(2);
    expect(
      screen.getAllByText(
        'Lab 3: Deploy and Operate Agents with Amazon Bedrock AgentCore',
      ).length,
    ).toBeGreaterThan(0);
  });

  it('renders an authenticated persisted turn record instead of session fixtures', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.includes('/governed-receipts/turn-live')) {
          return new Response(
            JSON.stringify({
              turn_id: 'turn-live',
              rail: 'gateway-mcp',
              citations: [
                {
                  evidence_id: 'retrieval-1-catalog-12',
                  source_uri: 'aurora://pellier/product_catalog/12',
                  revision: null,
                  quote: 'Linen Camp Shirt: Breathable resort layer',
                  entity_id: '12',
                },
              ],
              tool_audit_ids: [],
              policy_events: [{ decision: 'NOT_EVALUATED' }],
              terminal_status: 'complete',
              latency_ms: 24,
            }),
            { status: 200, headers: { 'Content-Type': 'application/json' } },
          );
        }
        return new Response(JSON.stringify(proofBoardPayload), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }),
    );

    render(
      <MemoryRouter initialEntries={['/observatory/proof-board?turn=turn-live']}>
        <ProofBoard />
      </MemoryRouter>,
    );

    expect(await screen.findByTestId('persisted-turn-receipt')).toHaveTextContent(
      'turn-live',
    );
    expect(screen.getByTestId('persisted-turn-receipt')).toHaveTextContent(
      'Linen Camp Shirt: Breathable resort layer',
    );
    expect(screen.getByTestId('persisted-turn-receipt')).toHaveTextContent(
      'NOT EVALUATED',
    );
  });

  it('renders a partial persisted receipt without crashing the evidence view', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) => {
        if (String(input).includes('/governed-receipts/turn-partial')) {
          return new Response(
            JSON.stringify({
              turn_id: 'turn-partial',
              rail: 'gateway-mcp',
              terminal_status: 'failed',
              latency_ms: null,
            }),
            { status: 200, headers: { 'Content-Type': 'application/json' } },
          );
        }
        return new Response(JSON.stringify(proofBoardPayload), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }),
    );

    render(
      <MemoryRouter initialEntries={['/observatory/proof-board?turn=turn-partial']}>
        <ProofBoard />
      </MemoryRouter>,
    );

    expect(await screen.findByTestId('persisted-turn-receipt')).toHaveTextContent(
      'turn-partial',
    );
    expect(screen.getByTestId('persisted-turn-receipt')).toHaveTextContent(
      '0 catalog citations',
    );
  });

  it('renders Audit Proof as a focused Lab 3 evidence view', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        new Response(JSON.stringify(proofBoardPayload), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
      ),
    );

    render(
      <MemoryRouter initialEntries={['/observatory/audit-proof']}>
        <ProofBoard focusCardId="audit-ledger" />
      </MemoryRouter>,
    );

    expect(await screen.findByText('Proof Board')).toBeInTheDocument();
    expect(await screen.findByTestId('proof-card-audit-ledger')).toHaveTextContent(
      'Prove the audit trail in Aurora',
    );
    expect(screen.getByText('SQL fallback')).toBeInTheDocument();
    expect(
      screen.getByText(
        'SELECT audit_id, caller, tool_name FROM pellier.tool_audit ORDER BY audit_id DESC;',
      ),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole('region', { name: 'Workshop readiness' }),
    ).not.toBeInTheDocument();
    expect(screen.queryByTestId('proof-card-marco-floor-check')).not.toBeInTheDocument();
    expect(screen.queryByTestId('proof-card-managed-rail')).not.toBeInTheDocument();
    expect(screen.queryByText('Lab checkpoints')).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'All checkpoints' })).toHaveAttribute(
      'href',
      '/observatory/proof-board',
    );
  });
});
