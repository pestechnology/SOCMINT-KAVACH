export interface RawProfile {
  type: string;
  value: string;
  platform: string;
  source_url: string;
  metadata?: Record<string, any>;
  data_mode: string;
  collected_at: string;
  sha256: string;
}

export interface SignalScore {
  signal_name: string;
  weight: number;
  matched: boolean;
  detail: string;
}

export interface LinkedIdentity {
  cluster_id: string;
  profiles: RawProfile[];
  signals: SignalScore[];
  confidence_score: number;
  tier: string;
  is_red_herring: boolean;
  red_herring_reason?: string;
  why_explanation: string[];
}

export interface InvestigationResponse {
  status: string;
  profile_count: number;
  profiles: RawProfile[];
  cluster_count: number;
  clusters: LinkedIdentity[];
}
