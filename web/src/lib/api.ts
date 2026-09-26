/**
 * Airmate Typed API Client
 * 
 * Base URL defaults to process.env.NEXT_PUBLIC_API_URL ?? "".
 * When empty, requests are made to the current origin (which is how FastAPI serves web/out).
 */

import type {
  AirReportIn,
  AirReportOut,
  BuddyStatusOut,
  ChatIn,
  ChatOut,
  CheckinAnswerIn,
  CheckinAnswerOut,
  DeviceEventIn,
  DeviceIn,
  DeviceOut,
  EmergencyIn,
  EmergencyOut,
  EventOut,
  HealthOut,
  HotspotsOut,
  IngestOut,
  MatchOut,
  NudgeAckIn,
  PairIn,
  PostIn,
  PostOut,
  PuffIn,
  ReadingBatchIn,
  ReadingPoint,
  ReportIn,
  ReportLinkOut,
  ReportOut,
  RiskBrief,
  RiskOut,
  RiskPoint,
  SymptomIn,
  UserOut,
  UserPatch,
} from "./types";

export const API_BASE = (process.env.NEXT_PUBLIC_API_URL ?? "").replace(/\/+$/, "");

export class ApiError extends Error {
  constructor(
    public status: number,
    public statusText: string,
    public data: unknown,
    url: string
  ) {
    super(`API Error ${status} (${statusText}) for ${url}`);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const url = `${API_BASE}${path.startsWith("/") ? path : `/${path}`}`;
  const headers = new Headers(init?.headers);

  if (init?.body && !headers.has("Content-Type") && typeof init.body === "string") {
    headers.set("Content-Type", "application/json");
  }

  const res = await fetch(url, {
    ...init,
    headers,
  });

  if (!res.ok) {
    let errorData: unknown = null;
    try {
      errorData = await res.json();
    } catch {
      errorData = await res.text();
    }
    throw new ApiError(res.status, res.statusText, errorData, url);
  }

  // Handle empty or 204 responses
  if (res.status === 204) {
    return {} as T;
  }

  return (await res.json()) as T;
}

export const api = {
  // ---- Health ----
  getHealth(): Promise<HealthOut> {
    return request<HealthOut>("/api/health");
  },

  // ---- Users ----
  getUsers(): Promise<UserOut[]> {
    return request<UserOut[]>("/api/users");
  },

  getUser(userId: string): Promise<UserOut> {
    return request<UserOut>(`/api/users/${encodeURIComponent(userId)}`);
  },

  patchUser(userId: string, patch: UserPatch): Promise<UserOut> {
    return request<UserOut>(`/api/users/${encodeURIComponent(userId)}`, {
      method: "PATCH",
      body: JSON.stringify(patch),
    });
  },

  getUserRisk(userId: string, fresh = false): Promise<RiskOut> {
    const q = fresh ? "?fresh=true" : "";
    return request<RiskOut>(`/api/users/${encodeURIComponent(userId)}/risk${q}`);
  },

  getUserRiskHistory(userId: string, hours = 24): Promise<RiskPoint[]> {
    return request<RiskPoint[]>(
      `/api/users/${encodeURIComponent(userId)}/risk/history?hours=${hours}`
    );
  },

  getUserReadings(userId: string, hours = 6): Promise<ReadingPoint[]> {
    return request<ReadingPoint[]>(
      `/api/users/${encodeURIComponent(userId)}/readings?hours=${hours}`
    );
  },

  getUserEvents(
    userId: string,
    params?: { kinds?: string; since?: number; limit?: number }
  ): Promise<EventOut[]> {
    const search = new URLSearchParams();
    if (params?.kinds) search.set("kinds", params.kinds);
    if (params?.since != null) search.set("since", String(params.since));
    if (params?.limit != null) search.set("limit", String(params.limit));
    const qs = search.toString();
    return request<EventOut[]>(
      `/api/users/${encodeURIComponent(userId)}/events${qs ? `?${qs}` : ""}`
    );
  },

  logPuff(userId: string, body: PuffIn = { count: 1 }): Promise<EventOut> {
    return request<EventOut>(`/api/users/${encodeURIComponent(userId)}/puffs`, {
      method: "POST",
      body: JSON.stringify(body),
    });
  },

  logSymptom(userId: string, body: SymptomIn): Promise<EventOut> {
    return request<EventOut>(`/api/users/${encodeURIComponent(userId)}/symptoms`, {
      method: "POST",
      body: JSON.stringify(body),
    });
  },

  // ---- Devices ----
  getDevices(): Promise<DeviceOut[]> {
    return request<DeviceOut[]>("/api/devices");
  },

  updateDevice(deviceId: string, body: DeviceIn): Promise<DeviceOut> {
    return request<DeviceOut>(`/api/devices/${encodeURIComponent(deviceId)}`, {
      method: "PUT",
      body: JSON.stringify(body),
    });
  },

  postReadings(
    deviceId: string,
    body: ReadingBatchIn,
    deviceKey?: string
  ): Promise<IngestOut> {
    const headers: Record<string, string> = {};
    if (deviceKey) headers["X-Device-Key"] = deviceKey;
    return request<IngestOut>(`/api/devices/${encodeURIComponent(deviceId)}/readings`, {
      method: "POST",
      headers,
      body: JSON.stringify(body),
    });
  },

  postDeviceEvent(
    deviceId: string,
    body: DeviceEventIn
  ): Promise<{ ok: boolean; id: number; risk?: RiskBrief | null }> {
    return request<{ ok: boolean; id: number; risk?: RiskBrief | null }>(
      `/api/devices/${encodeURIComponent(deviceId)}/events`,
      {
        method: "POST",
        body: JSON.stringify(body),
      }
    );
  },

  // ---- Agent & Safety (A1) ----
  chat(body: ChatIn): Promise<ChatOut> {
    return request<ChatOut>("/api/agent/chat", {
      method: "POST",
      body: JSON.stringify(body),
    });
  },

  answerCheckin(checkinId: number, body: CheckinAnswerIn): Promise<CheckinAnswerOut> {
    return request<CheckinAnswerOut>(`/api/checkins/${checkinId}/answer`, {
      method: "POST",
      body: JSON.stringify(body),
    });
  },

  triggerEmergency(userId: string, body: EmergencyIn): Promise<EmergencyOut> {
    return request<EmergencyOut>(`/api/users/${encodeURIComponent(userId)}/emergency`, {
      method: "POST",
      body: JSON.stringify(body),
    });
  },

  // ---- Community (A4) ----
  getHotspots(hours = 6): Promise<HotspotsOut> {
    return request<HotspotsOut>(`/api/community/hotspots?hours=${hours}`);
  },

  reportAir(body: AirReportIn): Promise<AirReportOut> {
    return request<AirReportOut>("/api/community/reports", {
      method: "POST",
      body: JSON.stringify(body),
    });
  },

  getCirclePosts(circleId: string): Promise<PostOut[]> {
    return request<PostOut[]>(`/api/circles/${encodeURIComponent(circleId)}/posts`);
  },

  addCirclePost(circleId: string, body: PostIn): Promise<PostOut> {
    return request<PostOut>(`/api/circles/${encodeURIComponent(circleId)}/posts`, {
      method: "POST",
      body: JSON.stringify(body),
    });
  },

  // ---- Buddy (A4) ----
  getBuddyStatus(userId: string): Promise<BuddyStatusOut> {
    return request<BuddyStatusOut>(`/api/users/${encodeURIComponent(userId)}/buddy`);
  },

  getBuddyMatches(userId: string): Promise<MatchOut[]> {
    return request<MatchOut[]>(`/api/buddy/matches?user_id=${encodeURIComponent(userId)}`);
  },

  pairBuddy(body: PairIn): Promise<{ ok: boolean }> {
    return request<{ ok: boolean }>("/api/buddy/pair", {
      method: "POST",
      body: JSON.stringify(body),
    });
  },

  ackNudge(alertId: number, body: NudgeAckIn): Promise<{ ok: boolean }> {
    return request<{ ok: boolean }>(`/api/buddy/nudges/${alertId}/ack`, {
      method: "POST",
      body: JSON.stringify(body),
    });
  },

  // ---- Doctor Report (A4) ----
  createReport(userId: string, body: ReportIn): Promise<ReportLinkOut> {
    return request<ReportLinkOut>(`/api/users/${encodeURIComponent(userId)}/reports`, {
      method: "POST",
      body: JSON.stringify(body),
    });
  },

  getReport(token: string): Promise<ReportOut> {
    return request<ReportOut>(`/api/reports/${encodeURIComponent(token)}`);
  },
};
