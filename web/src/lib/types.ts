/**
 * Airmate TypeScript Type Definitions
 * 
 * Mirror of docs/API.md and backend/airmate_api/schemas.py.
 * Changing any shape here requires coordination with docs/API.md and the backend lead (A0).
 */

export type Band = "low" | "elevated" | "high";

export const BAND_COLORS: Record<Band, string> = {
  low: "#10b981",
  elevated: "#f59e0b",
  high: "#ef4444",
} as const;

export type SymptomKind =
  | "cough"
  | "wheeze"
  | "chest_tight"
  | "short_breath"
  | "night_waking"
  | "other";

export type TriggerKind =
  | "dust"
  | "smoke"
  | "pollen"
  | "humidity"
  | "odors"
  | "cold_air";

export const DEMO_USERS = ["maya", "jordan", "priya"] as const;
export type DemoUserId = (typeof DEMO_USERS)[number];

// ---- Device & Sensor Readings ----

export interface ReadingIn {
  ts?: number | null;
  age_s?: number | null;
  pm25?: number | null;
  pm10?: number | null;
  co2?: number | null;
  tvoc?: number | null;
  temp_c?: number | null;
  humidity?: number | null;
}

export interface ReadingBatchIn {
  readings: ReadingIn[];
  fw?: string | null;
  rssi?: number | null;
}

export interface RiskBrief {
  score: number;
  band: Band;
  color: string;
  ts: number;
}

export interface IngestOut {
  user_id: string | null;
  accepted: number;
  risk?: RiskBrief | null;
}

export interface DeviceEventIn {
  kind: "button" | "puff" | "cough";
  ts?: number | null;
  data?: Record<string, unknown>;
}

export interface DeviceIn {
  user_id?: string | null;
  label?: string | null;
  lat?: number | null;
  lon?: number | null;
  community?: boolean;
}

export interface DeviceOut extends DeviceIn {
  id: string;
  last_seen?: number | null;
}

// ---- Users, Action Plan, Risk, Events ----

export interface ActionPlanZone {
  when: string;
  do: string[];
}

export interface ActionPlan {
  controller?: string;
  rescue?: string;
  green?: ActionPlanZone;
  yellow?: ActionPlanZone;
  red?: ActionPlanZone;
  notes?: string;
  [key: string]: unknown;
}

export interface EmergencyContact {
  name?: string;
  phone?: string;
  relation?: string;
  [key: string]: unknown;
}

export interface UserOut {
  id: string;
  name: string;
  role: string;
  age?: number | null;
  lat?: number | null;
  lon?: number | null;
  neighborhood?: string | null;
  tz: string;
  triggers: string[];
  action_plan: ActionPlan;
  buddy_id?: string | null;
  caregiver_ids: string[];
  cares_for_id?: string | null;
  circle_id?: string | null;
  doctor_name?: string | null;
  doctor_email?: string | null;
  phone?: string | null;
  emergency_contact: EmergencyContact;
  bio?: string | null;
}

export interface UserPatch {
  name?: string | null;
  age?: number | null;
  lat?: number | null;
  lon?: number | null;
  neighborhood?: string | null;
  tz?: string | null;
  triggers?: string[] | null;
  action_plan?: ActionPlan | null;
  buddy_id?: string | null;
  doctor_name?: string | null;
  doctor_email?: string | null;
  phone?: string | null;
  emergency_contact?: EmergencyContact | null;
  bio?: string | null;
}

export interface PuffIn {
  count?: number;
  ts?: number | null;
  source?: string;
}

export interface SymptomIn {
  symptom: SymptomKind;
  severity?: number;
  note?: string | null;
  ts?: number | null;
  source?: string;
}

export interface EventOut {
  id: number;
  user_id: string | null;
  device_id: string | null;
  kind: string; // reading, puff, symptom, button, cough, risk, checkin, alert, emergency, chat, alert_ack, air_report
  ts: number;
  data: Record<string, unknown>;
  lat?: number | null;
  lon?: number | null;
}

export interface Factor {
  key: string;
  label: string;
  points: number;
  detail?: string | null;
}

export interface RiskOut {
  user_id: string;
  ts: number;
  score: number;
  band: Band;
  color: string;
  probabilities?: {
    "1h": number;
    "4h": number;
    "12h": number;
  } | null;
  factors: Factor[];
  latest: {
    pm25?: number | null;
    pm10?: number | null;
    co2?: number | null;
    tvoc?: number | null;
    temp_c?: number | null;
    humidity?: number | null;
    [sensor: string]: number | null | undefined;
  };
  normal: {
    pm25?: number;
    pm10?: number;
    tvoc?: number;
    [sensor: string]: number | undefined;
  };
  ratios: {
    pm25?: number;
    pm10?: number;
    tvoc?: number;
    [sensor: string]: number | undefined;
  };
  sensors_available: string[];
  outdoor: {
    aqi?: number | null;
    pollen?: number | null;
    temp_c?: number | null;
    humidity?: number | null;
    [key: string]: number | null | undefined;
  };
  puffs_24h: number;
  symptoms_24h: number;
  normal_day_score?: number | null;
  rule_score: number;
  model: {
    name?: string;
    trained_on?: string;
    [key: string]: unknown;
  };
}

export interface RiskPoint {
  ts: number;
  score: number;
  band: Band;
}

export interface ReadingPoint {
  ts: number;
  pm25?: number | null;
  pm10?: number | null;
  co2?: number | null;
  tvoc?: number | null;
  temp_c?: number | null;
  humidity?: number | null;
}

export interface HealthOut {
  ok: boolean;
  ts: number;
  model: Record<string, unknown>;
  grok: boolean;
  database: string;
}

// ---- Agent (A1) ----

export interface ChatIn {
  user_id: string;
  message: string;
  conversation_id?: string | null;
  speak?: boolean;
}

export interface ChatToolCall {
  name: string;
  arguments: Record<string, unknown>;
  result?: unknown;
}

export interface ChatOut {
  reply: string;
  conversation_id?: string | null;
  emergency: boolean;
  red_flags: string[];
  tool_calls: ChatToolCall[];
  audio_url?: string | null;
}

export interface TtsIn {
  text: string;
  voice?: string | null;
}

export interface CheckinAnswerIn {
  user_id: string;
  answer: "ok" | "not_ok" | "used_inhaler" | string;
}

export interface CheckinAnswerOut {
  ok: boolean;
  reply?: string;
  emergency?: boolean;
}

export interface EmergencyIn {
  text?: string | null;
  lat?: number | null;
  lon?: number | null;
}

export interface EmergencyOut {
  ok: boolean;
  script: string;
  notified: string[];
}

// ---- Community (A4) ----

export interface HotspotCell {
  lat: number;
  lon: number;
  score: number;
  aqi?: number | null;
  pm25?: number | null;
  pm10?: number | null;
  tvoc?: number | null;
  contributors: number;
  puffs: number;
  reports: string[];
  label?: string | null;
}

export interface HotspotsOut {
  generated_at: number;
  hours: number;
  cells: HotspotCell[];
}

export interface AirReportIn {
  user_id?: string | null;
  lat: number;
  lon: number;
  kind: "smoke" | "dust" | "pollen" | "odor" | "construction" | "other";
  note?: string | null;
}

export interface AirReportOut {
  ok: boolean;
  id: number;
}

export interface PostIn {
  user_id: string;
  text: string;
}

export interface PostOut {
  id: number;
  circle_id: string;
  user_id: string;
  user_name: string;
  text: string;
  ts: number;
}

// ---- Buddy (A4) ----

export interface BuddyPerson {
  id: string;
  name: string;
  neighborhood?: string | null;
  triggers: string[];
  risk?: RiskBrief | null;
  last_seen?: number | null;
}

export interface BuddyStatusOut {
  me: BuddyPerson;
  buddy?: BuddyPerson | null;
  open_nudges: Record<string, unknown>[];
}

export interface MatchOut {
  user_id: string;
  name: string;
  score: number;
  reasons: string[];
}

export interface PairIn {
  user_id: string;
  buddy_id: string;
}

export interface NudgeAckIn {
  user_id: string;
  action: "on_my_way" | "calling" | "checked_ok";
}

// ---- Doctor Report (A4) ----

export interface ReportIn {
  days?: number;
  send_to?: string | null;
}

export interface ReportLinkOut {
  token: string;
  url: string;
}

export interface DailyRow {
  date: string;
  puffs: number;
  symptoms: number;
  max_score: number;
  mean_score: number;
  night_symptoms: number;
}

export interface ReportOut {
  token: string;
  created_at: number;
  user: Record<string, unknown>;
  period_days: number;
  summary: string;
  totals: Record<string, unknown>;
  daily: DailyRow[];
  top_factors: { key: string; label: string; share: number }[];
  exposure_notes: string[];
  disclaimer: string;
}

// ---- Live Stream Message Types (docs/API.md: Live stream) ----

export interface HelloStreamData {
  topics: string[];
}

export interface ReadingStreamData {
  device_id: string;
  ts: number;
  pm25?: number | null;
  pm10?: number | null;
  co2?: number | null;
  tvoc?: number | null;
  temp_c?: number | null;
  humidity?: number | null;
  lat?: number | null;
  lon?: number | null;
}

export type RiskStreamData = RiskOut;

export interface EventStreamData {
  id: number;
  kind: string;
  ts: number;
  data: Record<string, unknown>;
}

export interface CheckinStreamData {
  id: number;
  ts: number;
  score: number;
  previous_score: number;
  reason: "jump" | "high";
  factor: Factor | null;
  message: string;
  audio_url: string | null;
  expires_at: number;
}

export interface CheckinUpdateStreamData {
  id: number;
  status: "answered" | "missed" | "escalated";
  answer: string | null;
}

export interface ChatStreamData {
  role: "assistant" | "user";
  text: string;
  source: "voice" | "chat" | "checkin";
}

export interface EmergencyStreamData {
  user_id: string;
  name: string;
  red_flags: string[];
  script: string;
  lat?: number | null;
  lon?: number | null;
  ts: number;
}

export interface BuddyNudgeStreamData {
  alert_id: number;
  for_user_id: string;
  for_name: string;
  score: number;
  factor?: Factor | null;
  checkin_id: number;
  message: string;
  ts: number;
}

export interface BuddyAckStreamData {
  alert_id: number;
  by_user_id: string;
  by_name: string;
  action: "on_my_way" | "calling" | "checked_ok";
}

export interface CommunityStreamData {
  kind: "report" | "hotspots";
  [key: string]: unknown;
}

export type StreamEventDataMap = {
  hello: HelloStreamData;
  reading: ReadingStreamData;
  risk: RiskStreamData;
  event: EventStreamData;
  checkin: CheckinStreamData;
  checkin_update: CheckinUpdateStreamData;
  chat: ChatStreamData;
  emergency: EmergencyStreamData;
  buddy_nudge: BuddyNudgeStreamData;
  buddy_ack: BuddyAckStreamData;
  community: CommunityStreamData;
};

export type StreamEventType = keyof StreamEventDataMap;

export interface StreamEnvelope<T = unknown> {
  type: string;
  topic?: string;
  ts: number;
  data: T;
}

export type TypedStreamMessage =
  | { type: "hello"; topic?: string; ts: number; data: HelloStreamData }
  | { type: "reading"; topic: string; ts: number; data: ReadingStreamData }
  | { type: "risk"; topic: string; ts: number; data: RiskStreamData }
  | { type: "event"; topic: string; ts: number; data: EventStreamData }
  | { type: "checkin"; topic: string; ts: number; data: CheckinStreamData }
  | { type: "checkin_update"; topic: string; ts: number; data: CheckinUpdateStreamData }
  | { type: "chat"; topic: string; ts: number; data: ChatStreamData }
  | { type: "emergency"; topic: string; ts: number; data: EmergencyStreamData }
  | { type: "buddy_nudge"; topic: string; ts: number; data: BuddyNudgeStreamData }
  | { type: "buddy_ack"; topic: string; ts: number; data: BuddyAckStreamData }
  | { type: "community"; topic: string; ts: number; data: CommunityStreamData }
  | { type: string; topic?: string; ts: number; data: unknown };
