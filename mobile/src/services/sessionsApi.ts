import Constants from 'expo-constants';

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
    throw new Error(body.detail ?? 'Erreur inconnue');
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
    headers: { Authorization: `Bearer ${token}` },
  });
  return handleResponse<JoinSessionResponse>(res);
}
