import Constants from 'expo-constants';

const API_URL: string =
  (Constants.expoConfig?.extra?.apiUrl as string | undefined) ?? 'http://localhost:8000';

export interface PendingInvitation {
  invitationId: string;
  sessionId: string;
  livekitRoomName: string;
  hostPhone: string;
  joinToken: string;
  createdAt: string;
  expiresAt: string;
}

export interface InvitationResult {
  invitationId: string;
  invitationType: 'salon_friend' | 'sms_contact';
  guestPhone: string;
  status: string;
  joinLink: string | null;
}

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(body.detail ?? 'Erreur inconnue');
  }
  return res.json() as Promise<T>;
}

export async function getMyInvitations(token: string): Promise<PendingInvitation[]> {
  const res = await fetch(`${API_URL}/me/invitations`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  return handleResponse<PendingInvitation[]>(res);
}

export async function sendInvitation(
  token: string,
  sessionId: string,
  guestPhoneNumber: string,
): Promise<InvitationResult> {
  const res = await fetch(`${API_URL}/sessions/${sessionId}/invitations`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
    body: JSON.stringify({ guestPhoneNumber }),
  });
  return handleResponse<InvitationResult>(res);
}
