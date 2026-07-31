import Constants from 'expo-constants';

// EXPO_PUBLIC_ vars are replaced at build time by Expo; Constants.expoConfig is the runtime alternative
const API_URL: string =
  (Constants.expoConfig?.extra?.apiUrl as string | undefined) ?? 'http://localhost:8000';

export interface AuthTokenResponse {
  token: string;
  userId: string;
}

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(body.detail ?? 'Erreur inconnue');
  }
  return res.json() as Promise<T>;
}

export async function requestOtp(email: string): Promise<void> {
  const res = await fetch(`${API_URL}/auth/otp/request`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email }),
  });
  await handleResponse<{ message: string }>(res);
}

export async function resendOtp(email: string): Promise<void> {
  const res = await fetch(`${API_URL}/auth/otp/resend`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email }),
  });
  await handleResponse<{ message: string }>(res);
}

export async function verifyOtp(email: string, code: string): Promise<AuthTokenResponse> {
  const res = await fetch(`${API_URL}/auth/otp/verify`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, code }),
  });
  return handleResponse<AuthTokenResponse>(res);
}
