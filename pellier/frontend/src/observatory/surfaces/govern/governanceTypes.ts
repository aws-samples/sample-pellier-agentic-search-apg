export interface IdentityObservation {
  state: 'anonymous' | 'verified';
  observedAt: string;
  caller: {
    username: string;
    subjectFingerprint: string;
    tokenFingerprint: string;
    tokenUse: string;
    expiresAt: number;
    issuer: string;
    clientId: string;
    customerClaim: string | null;
    staffScope: string | null;
    operatorGroup: boolean;
  } | null;
}

export interface PolicyObservation {
  id: string;
  name: string;
  description: string;
  mode: 'ACTIVE' | 'LOG_ONLY' | null;
  cedar: string | null;
  definitionHash: string | null;
  definitionState: 'observed' | 'unavailable';
}

export interface PolicySnapshot {
  observedAt: string;
  source: 'managed-engine' | 'not-configured' | 'unavailable';
  engineId: string | null;
  gatewayMode: 'ENFORCE' | 'LOG_ONLY' | null;
  gatewayState: 'observed' | 'not-configured' | 'unavailable';
  attachmentMatches: boolean | null;
  policies: PolicyObservation[];
  complete: boolean;
  labPolicyState: 'present' | 'not-observed' | 'unknown';
  checkout: {
    revision: string | null;
    modified: boolean | null;
    source: 'checkout' | 'deployment-declaration';
  };
}
