import Constants from 'expo-constants';

const API_URL: string =
  (Constants.expoConfig?.extra?.apiUrl as string | undefined) ?? 'http://localhost:8000';

export interface UserProfile {
  userId: string;
  email: string;
  phoneNumber?: string | null;
  detectedLanguage: string | null;
  /**
   * The two languages this person chose, as opposed to detectedLanguage, which is what the
   * agent heard them speaking. null means never chosen — and for captions that differs from
   * '', which is the "as spoken" option and a real decision to read nothing translated.
   */
  interfaceLanguage: string | null;
  captionLanguage: string | null;
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

/**
 * Remember a language choice on the account, so it follows the person to their other devices.
 *
 * Each field is sent only when it is being changed: the two controls are separate on screen,
 * and a request carrying both would let one overwrite a choice the reader did not touch.
 */
export async function saveLanguagePreferences(
  token: string,
  prefs: { interfaceLanguage?: string; captionLanguage?: string },
): Promise<UserProfile> {
  const res = await fetch(`${API_URL}/me/preferences`, {
    method: 'PATCH',
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(prefs),
  });
  return handleResponse<UserProfile>(res);
}
