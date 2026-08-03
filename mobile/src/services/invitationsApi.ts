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
  /** Either may be empty — never both. A guest reached only by text has no address. */
  guestEmail: string;
  guestPhone: string;
  status: string;
  /** Always present: a join token is minted for every type, members included. */
  joinLink: string;
  /** Whether SES accepted the invitation email. A false here is not an error — the
   *  invitation exists and the link above works over any channel. */
  emailSent: boolean;
  /** Same for the text message. Reported separately so a host who supplied both is not
   *  told "sent" when only one of the two actually left. */
  smsSent: boolean;
  /** The LiveKit identity this guest will join under, known before they connect —
   *  the handle to address a message to this guest rather than to the whole room. */
  participantIdentity: string;
  /** How the guest is labelled to everyone in the room, e.g. "Guest 3F2A". Derived
   *  from the identity, never from their email. */
  participantName: string;
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

/**
 * Invite someone by email, by text message, or by both.
 *
 * One of the two is required. A blank field is omitted rather than sent as an empty
 * string: '' is not an address, and the API would otherwise have to guess whether it was
 * a channel the host meant to use.
 */
export async function sendInvitation(
  token: string,
  sessionId: string,
  guestEmail?: string,
  guestPhone?: string,
): Promise<InvitationResult> {
  const res = await fetch(`${API_URL}/sessions/${sessionId}/invitations`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
    body: JSON.stringify({
      ...(guestEmail ? { guestEmail } : {}),
      ...(guestPhone ? { guestPhone } : {}),
    }),
  });
  return handleResponse<InvitationResult>(res);
}
