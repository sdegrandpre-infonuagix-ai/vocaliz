import Constants from 'expo-constants';
import { deviceType } from './deviceType';

const API_URL: string =
  (Constants.expoConfig?.extra?.apiUrl as string | undefined) ?? 'http://localhost:8000';

export interface SessionResponse {
  sessionId: string;
  livekitRoomName: string;
  hostToken: string;
  sourceType: string;
  createdAt: string;
}

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(body.detail ?? 'Unknown error');
  }
  return res.json() as Promise<T>;
}

export async function createSessionFromUrl(
  token: string,
  sourceUrl: string,
): Promise<SessionResponse> {
  const form = new FormData();
  form.append('source_url', sourceUrl);
  const res = await fetch(`${API_URL}/sessions`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
    body: form,
  });
  return handleResponse<SessionResponse>(res);
}

/**
 * Start a session with no document and no URL. The agent opens by asking the
 * participants what they would like to discuss.
 */
export async function createSessionWithoutSource(token: string): Promise<SessionResponse> {
  const res = await fetch(`${API_URL}/sessions`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
    body: new FormData(),
  });
  return handleResponse<SessionResponse>(res);
}

export async function createSessionFromFile(
  token: string,
  file: { uri: string; name: string; type: string },
): Promise<SessionResponse> {
  const form = new FormData();
  // React Native FormData accepts {uri, name, type} objects for file fields
  form.append('file', file as unknown as Blob);
  const res = await fetch(`${API_URL}/sessions`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
    body: form,
  });
  return handleResponse<SessionResponse>(res);
}

export interface SessionSourceResponse {
  sourceId: string;
  sessionId: string;
  sourceType: string;
  contentLength: number;
  createdAt: string;
}

export async function addSourceFromUrl(
  token: string,
  sessionId: string,
  sourceUrl: string,
): Promise<SessionSourceResponse> {
  const form = new FormData();
  form.append('source_url', sourceUrl);
  const res = await fetch(`${API_URL}/sessions/${sessionId}/sources`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
    body: form,
  });
  return handleResponse<SessionSourceResponse>(res);
}

export async function addSourceFromFile(
  token: string,
  sessionId: string,
  file: { uri: string; name: string; type: string },
): Promise<SessionSourceResponse> {
  const form = new FormData();
  form.append('file', file as unknown as Blob);
  const res = await fetch(`${API_URL}/sessions/${sessionId}/sources`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
    body: form,
  });
  return handleResponse<SessionSourceResponse>(res);
}

export interface JoinSessionResponse {
  participantToken: string;
  livekitRoomName: string;
  livekitUrl: string;
}

export async function joinSession(
  token: string,
  sessionId: string,
): Promise<JoinSessionResponse> {
  const res = await fetch(`${API_URL}/sessions/${sessionId}/join`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    // Sent by the client rather than derived from the User-Agent header: this app's requests
    // carry no browser header worth reading, and even on the web the header cannot tell an
    // iPad from a Mac.
    body: JSON.stringify({ device: deviceType() }),
  });
  return handleResponse<JoinSessionResponse>(res);
}

/**
 * Metering heartbeat (Story 4.2). The agent sends these too; the client sends its own so
 * host time keeps accruing even if the agent worker drops out mid-session.
 */
export async function sendHeartbeat(
  token: string,
  sessionId: string,
  seconds: number,
): Promise<void> {
  const res = await fetch(`${API_URL}/sessions/${sessionId}/heartbeat`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({ seconds }),
  });
  await handleResponse<unknown>(res);
}

export async function endSession(token: string, sessionId: string): Promise<void> {
  const res = await fetch(`${API_URL}/sessions/${sessionId}/end`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
  });
  await handleResponse<unknown>(res);
}

/**
 * What the host's agent control should show.
 *
 * Two independent facts rather than one tri-state: an agent can be present and listening,
 * present and paused, or absent, and "absent" and "paused" are undone differently.
 */
export interface AgentState {
  present: boolean;
  muted: boolean;
}

export async function getAgentState(token: string, sessionId: string): Promise<AgentState> {
  const res = await fetch(`${API_URL}/sessions/${sessionId}/agent`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  return handleResponse<AgentState>(res);
}

/**
 * Pause or activate the agent. A Salon starts paused, so the first call of the session is
 * what opens the conversation rather than what resumes it.
 */
export async function setAgentMuted(
  token: string,
  sessionId: string,
  muted: boolean,
): Promise<AgentState> {
  const res = await fetch(`${API_URL}/sessions/${sessionId}/agent/mute`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({ muted }),
  });
  return handleResponse<AgentState>(res);
}
