import Constants from 'expo-constants';

const API_URL = Constants.expoConfig?.extra?.apiUrl ?? process.env.EXPO_PUBLIC_API_URL ?? 'http://localhost:8000';

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

export async function requestOtp(phoneNumber: string): Promise<void> {
  const res = await fetch(`${API_URL}/auth/otp/request`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ phoneNumber }),
  });
  await handleResponse<{ message: string }>(res);
}

export async function resendOtp(phoneNumber: string): Promise<void> {
  const res = await fetch(`${API_URL}/auth/otp/resend`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ phoneNumber }),
  });
  await handleResponse<{ message: string }>(res);
}

export async function verifyOtp(phoneNumber: string, code: string): Promise<AuthTokenResponse> {
  const res = await fetch(`${API_URL}/auth/otp/verify`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ phoneNumber, code }),
  });
  return handleResponse<AuthTokenResponse>(res);
}
