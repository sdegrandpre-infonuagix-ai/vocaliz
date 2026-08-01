import Constants from 'expo-constants';

const API_URL: string =
  (Constants.expoConfig?.extra?.apiUrl as string | undefined) ?? 'http://localhost:8000';

export interface PendingInvitation {
  invitationId: string;
  sessionId: string;
  livekitRoomName: string;
  hostEmail: string;
  hostPhone?: string | null;
  joinToken: string;
  createdAt: string;
  expiresAt: string;
}

export interface InvitationResult {
  invitationId: string;
  /** 'sms_contact' no longer exists — sign-in moved to email and the API returns 'email_contact'. */
  invitationType: 'salon_friend' | 'email_contact';
  guestEmail: string;
  status: string;
  /** Always present: a join token is minted for every type, members included. */
  joinLink: string;
  /** Whether SES accepted the invitation email. A false here is not an error — the
   *  invitation exists and the link above works over any channel. */
  emailSent: boolean;
}

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(body.detail ?? 'Unknown error');
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
  guestEmail: string,
): Promise<InvitationResult> {
  const res = await fetch(`${API_URL}/sessions/${sessionId}/invitations`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
    body: JSON.stringify({ guestEmail }),
  });
  return handleResponse<InvitationResult>(res);
}
