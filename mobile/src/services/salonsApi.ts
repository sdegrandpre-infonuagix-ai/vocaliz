import Constants from 'expo-constants';
import { deviceType } from './deviceType';

const API_URL: string =
  (Constants.expoConfig?.extra?.apiUrl as string | undefined) ?? 'http://localhost:8000';

export interface SalonResponse {
  salonId: string;
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

export async function createSalonFromUrl(
  token: string,
  sourceUrl: string,
): Promise<SalonResponse> {
  const form = new FormData();
  form.append('source_url', sourceUrl);
  const res = await fetch(`${API_URL}/salons`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
    body: form,
  });
  return handleResponse<SalonResponse>(res);
}

/**
 * Start a salon with no document and no URL. The agent opens by asking the
 * participants what they would like to discuss.
 */
export async function createSalonWithoutSource(token: string): Promise<SalonResponse> {
  const res = await fetch(`${API_URL}/salons`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
    body: new FormData(),
  });
  return handleResponse<SalonResponse>(res);
}

export async function createSalonFromFile(
  token: string,
  file: { uri: string; name: string; type: string },
): Promise<SalonResponse> {
  const form = new FormData();
  // React Native FormData accepts {uri, name, type} objects for file fields
  form.append('file', file as unknown as Blob);
  const res = await fetch(`${API_URL}/salons`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
    body: form,
  });
  return handleResponse<SalonResponse>(res);
}

export interface SalonSourceResponse {
  sourceId: string;
  salonId: string;
  sourceType: string;
  contentLength: number;
  createdAt: string;
}

export async function addSourceFromUrl(
  token: string,
  salonId: string,
  sourceUrl: string,
): Promise<SalonSourceResponse> {
  const form = new FormData();
  form.append('source_url', sourceUrl);
  const res = await fetch(`${API_URL}/salons/${salonId}/sources`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
    body: form,
  });
  return handleResponse<SalonSourceResponse>(res);
}

export async function addSourceFromFile(
  token: string,
  salonId: string,
  file: { uri: string; name: string; type: string },
): Promise<SalonSourceResponse> {
  const form = new FormData();
  form.append('file', file as unknown as Blob);
  const res = await fetch(`${API_URL}/salons/${salonId}/sources`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
    body: form,
  });
  return handleResponse<SalonSourceResponse>(res);
}

export interface JoinSalonResponse {
  participantToken: string;
  livekitRoomName: string;
  livekitUrl: string;
}

export async function joinSalon(
  token: string,
  salonId: string,
): Promise<JoinSalonResponse> {
  const res = await fetch(`${API_URL}/salons/${salonId}/join`, {
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
  return handleResponse<JoinSalonResponse>(res);
}

/**
 * Metering heartbeat (Story 4.2). The agent sends these too; the client sends its own so
 * host time keeps accruing even if the agent worker drops out mid-salon.
 */
export async function sendHeartbeat(
  token: string,
  salonId: string,
  seconds: number,
): Promise<void> {
  const res = await fetch(`${API_URL}/salons/${salonId}/heartbeat`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({ seconds }),
  });
  await handleResponse<unknown>(res);
}

export async function endSalon(token: string, salonId: string): Promise<void> {
  const res = await fetch(`${API_URL}/salons/${salonId}/end`, {
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

export async function getAgentState(token: string, salonId: string): Promise<AgentState> {
  const res = await fetch(`${API_URL}/salons/${salonId}/agent`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  return handleResponse<AgentState>(res);
}

/**
 * Pause or activate the agent. A Salon starts paused, so the first call of the salon is
 * what opens the conversation rather than what resumes it.
 */
export async function setAgentMuted(
  token: string,
  salonId: string,
  muted: boolean,
): Promise<AgentState> {
  const res = await fetch(`${API_URL}/salons/${salonId}/agent/mute`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({ muted }),
  });
  return handleResponse<AgentState>(res);
}
