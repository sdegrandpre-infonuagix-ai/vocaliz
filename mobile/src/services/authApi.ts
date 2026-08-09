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
    throw new Error(body.detail ?? 'Unknown error');
  }
  return res.json() as Promise<T>;
}

// `name` is required to create an account and ignored when signing in to one — the API
// draws that line, because only it knows whether the address is already on file. Sent on
// every request rather than only the first: the client cannot tell a new address from a
// returning one, and guessing wrong locks somebody out of their own account.
export async function requestOtp(email: string, name?: string): Promise<void> {
  const res = await fetch(`${API_URL}/auth/otp/request`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, name }),
  });
  await handleResponse<{ message: string }>(res);
}

export async function resendOtp(email: string, name?: string): Promise<void> {
  const res = await fetch(`${API_URL}/auth/otp/resend`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, name }),
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
