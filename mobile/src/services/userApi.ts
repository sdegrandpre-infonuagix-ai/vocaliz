import Constants from 'expo-constants';

const API_URL: string =
  (Constants.expoConfig?.extra?.apiUrl as string | undefined) ?? 'http://localhost:8000';

export interface UserProfile {
  userId: string;
  email: string;
  phoneNumber?: string | null;
  detectedLanguage: string | null;
}

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(body.detail ?? 'Unknown error');
  }
  return res.json() as Promise<T>;
}

export async function getMyProfile(token: string): Promise<UserProfile> {
  const res = await fetch(`${API_URL}/me/profile`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  return handleResponse<UserProfile>(res);
}

export async function updateDetectedLanguage(token: string, language: string): Promise<UserProfile> {
  const res = await fetch(`${API_URL}/me/language`, {
    method: 'PATCH',
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ language }),
  });
  return handleResponse<UserProfile>(res);
}
