/**
 * In-session screen — the host's live room: microphone, agent audio, mid-session sources
 * (FR3) and guest invitations (FR2).
 * Palette: Salon Parisien (UX-DR1). WCAG AA touch targets (UX-DR7).
 */
import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  ActivityIndicator,
  AppState,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { StatusBar } from 'expo-status-bar';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Contact } from 'expo-contacts';
import { AudioSession } from '@livekit/react-native';
// livekit-client is pulled in by @livekit/react-native, which does not re-export Room;
// it is declared as a direct dependency so this import is not resting on hoisting.
import { Room, RoomEvent } from 'livekit-client';

import PoweredBy from '../components/PoweredBy';
import Wordmark from '../components/Wordmark';
import CaptionsPanel from '../components/CaptionsPanel';
import DrivingMode from '../components/DrivingMode';
import { colors, spacing, typography, MIN_TOUCH } from '../theme/tokens';
import { useAuth } from '../contexts/AuthContext';
import { useLanguage } from '../contexts/LanguageContext';
import { useTranslationMute } from '../hooks/useTranslationMute';
import { useCaptions } from '../hooks/useCaptions';
import {
  addSourceFromUrl,
  endSession,
  getAgentState,
  joinSession,
  sendHeartbeat,
  // Aliased because the component holds its own agent state, and a setter and a network call
  // sharing one name is the kind of collision that compiles in JavaScript and misbehaves.
  setAgentMuted as requestAgentMuted,
} from '../services/sessionsApi';
import { sendInvitation } from '../services/invitationsApi';
import { getPublicConfig } from '../services/configApi';
import { getMyProfile, saveLanguagePreferences } from '../services/userApi';

const HEARTBEAT_SECONDS = 30;

interface Props {
  sessionId: string;
  onLeft: () => void;
}

export default function RoomScreen({ sessionId, onLeft }: Props) {
  const { token } = useAuth();
  const { t } = useLanguage();

  const [room, setRoom] = useState<Room | null>(null);
  const [connecting, setConnecting] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [sourceUrl, setSourceUrl] = useState('');
  const [guestEmail, setGuestEmail] = useState('');
  const [guestPhone, setGuestPhone] = useState('');
  // Off until the server says otherwise. Text messaging waits on an AWS review, and a
  // field that produces nothing is worse than no field.
  const [smsEnabled, setSmsEnabled] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [joinLink, setJoinLink] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  // Driving mode is a toggle: on, the screen goes black and stays awake; off, the room
  // comes back exactly as it was. It changes nothing about the conversation itself.
  const [driving, setDriving] = useState(false);

  // Ref rather than state: the heartbeat interval must see the live room without
  // re-subscribing on every render.
  const roomRef = useRef<Room | null>(null);

  // Mutes the local mic while the agent reads a translation aloud (Story 2.10). This hook
  // existed long before anything created a Room for it — this is its first real caller.
  useTranslationMute(room);

  // Live captions. The chosen language travels to the agent as a participant attribute,
  // so it knows which languages to translate each turn into.
  const { captions, language: captionLang, setLanguage: setCaptionLang } = useCaptions(room);

  // A Salon starts with its agent paused, so this is the control that opens the conversation
  // as well as the one that interrupts it. Assumed paused until the API answers: showing
  // "listening" first would tell the host their agent can hear them before it can.
  const [agentMuted, setAgentMuted] = useState(true);
  const [agentBusy, setAgentBusy] = useState(false);

  useEffect(() => {
    if (!token) return;
    getAgentState(token, sessionId)
      .then((state) => setAgentMuted(state.muted))
      // The control keeps showing paused. A state that cannot be read is no reason to claim
      // the agent is listening.
      .catch(() => undefined);
  }, [token, sessionId]);

  const toggleAgent = useCallback(async () => {
    if (!token || agentBusy) return;
    setAgentBusy(true);
    try {
      const state = await requestAgentMuted(token, sessionId, !agentMuted);
      setAgentMuted(state.muted);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setAgentBusy(false);
    }
  }, [token, sessionId, agentMuted, agentBusy]);

  // Nobody reads while driving, so nothing is translated for them: the empty attribute
  // tells the agent to stop rendering turns this participant will never see. The choice
  // itself is untouched and comes back when the mode does.
  const chosenCaptionLang = useRef('');
  useEffect(() => {
    if (driving) {
      chosenCaptionLang.current = captionLang;
      if (captionLang) setCaptionLang('');
    } else if (chosenCaptionLang.current) {
      setCaptionLang(chosenCaptionLang.current);
      chosenCaptionLang.current = '';
    }
    // captionLang is deliberately absent: including it would re-run this on the very
    // change it just made, and clear the saved choice before it could be restored.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [driving, setCaptionLang]);

  // The caption language this person chose, from whichever device they chose it on.
  //
  // Applied once. Compared against null rather than falsy because '' is itself a choice here —
  // "as spoken" — and treating it as "nothing saved" would discard that decision every session.
  const adoptedCaptionLang = useRef(false);
  useEffect(() => {
    if (!token || adoptedCaptionLang.current) return;
    let stale = false;
    getMyProfile(token)
      .then((profile) => {
        if (stale || adoptedCaptionLang.current) return;
        adoptedCaptionLang.current = true;
        if (profile.captionLanguage !== null && profile.captionLanguage !== undefined) {
          setCaptionLang(profile.captionLanguage);
        }
      })
      .catch(() => {
        // A profile that will not load costs a preference, not a session.
      });
    return () => {
      stale = true;
    };
  }, [token, setCaptionLang]);

  // Only an explicit choice reaches the account. Driving mode clears the language and puts it
  // back when it exits, and routing that through here would save "as spoken" as a preference —
  // permanently, if the app were closed while driving.
  const chooseCaptionLang = useCallback(
    (next: string) => {
      setCaptionLang(next);
      if (!token) return;
      saveLanguagePreferences(token, { captionLanguage: next }).catch(() => {
        // Kept on the device regardless.
      });
    },
    [token, setCaptionLang],
  );

  useEffect(() => {
    let stale = false;
    getPublicConfig().then((cfg) => {
      if (!stale) setSmsEnabled(cfg.smsEnabled);
    });
    return () => {
      stale = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    let connected: Room | null = null;

    async function connect() {
      if (!token) return;
      try {
        // Required on native before connecting, otherwise the OS routes no audio at all.
        await AudioSession.startAudioSession();

        const creds = await joinSession(token, sessionId);
        const r = new Room();
        await r.connect(creds.livekitUrl, creds.participantToken);
        await r.localParticipant.setMicrophoneEnabled(true);

        if (cancelled) {
          await r.disconnect();
          return;
        }
        connected = r;
        roomRef.current = r;
        // Cleared per connection, not once per mount: the guard is armed by the cleanup below,
        // and a screen reused for a second session must be able to exit again.
        leaving.current = false;
        setRoom(r);
      } catch (e: any) {
        if (!cancelled) setError(e.message ?? t.room.errorConnect);
      } finally {
        if (!cancelled) setConnecting(false);
      }
    }

    connect();

    return () => {
      cancelled = true;
      // Armed before disconnecting. This cleanup runs before the one that removes the
      // Disconnected listener — React tears effects down in the order they were defined — so
      // without it, unmounting would report the salon as having ended under the user.
      leaving.current = true;
      if (connected) connected.disconnect().catch(() => {});
      roomRef.current = null;
      AudioSession.stopAudioSession().catch(() => {});
    };
  }, [sessionId, token, t.room.errorConnect]);

  // Metering (Story 4.2). Sent from the client as well as the agent so host time keeps
  // accruing even if the agent worker drops out.
  useEffect(() => {
    if (!room || !token) return;
    const id = setInterval(() => {
      sendHeartbeat(token, sessionId, HEARTBEAT_SECONDS).catch(() => {
        // A missed heartbeat costs a little accuracy; it must not interrupt the session.
      });
    }, HEARTBEAT_SECONDS * 1000);
    return () => clearInterval(id);
  }, [room, token, sessionId]);

  // Backgrounding the app is how a phone session really ends — the host swipes away or
  // locks the screen rather than tapping Leave. Disconnecting stops the heartbeats and
  // empties the room, which the agent watches to close the session server-side.
  useEffect(() => {
    const sub = AppState.addEventListener('change', state => {
      if (state === 'background' && roomRef.current) {
        roomRef.current.disconnect().catch(() => {});
        roomRef.current = null;
        setRoom(null);
      }
    });
    return () => sub.remove();
  }, []);

  const handleAddSource = useCallback(async () => {
    if (!token || !sourceUrl.trim()) return;
    setBusy(true);
    setNotice(null);
    try {
      await addSourceFromUrl(token, sessionId, sourceUrl.trim());
      setSourceUrl('');
      setNotice(t.room.sourceAdded);
    } catch (e: any) {
      setError(e.message ?? t.room.errorGeneric);
    } finally {
      setBusy(false);
    }
  }, [token, sessionId, sourceUrl, t.room]);

  /**
   * Fill the fields from the phone's own address book.
   *
   * The native picker rather than a list we build: it needs no permission on iOS beyond
   * the single contact the person chose, it is the interface they already know, and it
   * spares us reading an entire address book to display it.
   *
   * Whatever the contact carries is taken — an address, a number, or both — because
   * either is enough to invite them and both is better.
   */
  const handlePickContact = useCallback(async () => {
    try {
      const contact = await Contact.presentPicker();
      if (!contact) return;
      // Fetched rather than read off the instance: the picker hands back a handle, and
      // the details are loaded on demand so choosing a contact does not pull their whole
      // record into memory.
      const [emails, phones] = await Promise.all([contact.getEmails(), contact.getPhones()]);
      const email = emails[0]?.address;
      // Only taken when the channel is offered. Filling a field the host cannot see
      // would send by a route they never chose.
      const phone = smsEnabled ? phones[0]?.number : undefined;
      if (email) setGuestEmail(email.trim().toLowerCase());
      if (phone) setGuestPhone(phone.trim());
      if (!email && !phone) setNotice(t.room.contactHasNoContact);
    } catch {
      // Declining the picker is not a failure, and neither is a device without contacts.
      // Either way the fields can still be typed by hand.
    }
  }, [t.room, smsEnabled]);

  const handleInvite = useCallback(async () => {
    const email = guestEmail.trim().toLowerCase();
    // A value left over from before the flag was read must not travel as a channel the
    // host did not choose.
    const phone = smsEnabled ? guestPhone.trim() : '';
    if (!token || (!email && !phone)) return;
    setBusy(true);
    setNotice(null);
    setJoinLink(null);
    try {
      const invite = await sendInvitation(token, sessionId, email || undefined, phone || undefined);
      setGuestEmail('');
      setGuestPhone('');
      // The link comes back whatever happens, so it is shown before any verdict on
      // delivery. Each channel is then reported on its own: a host who supplied both
      // must not read "sent" when only one of the two actually left.
      setJoinLink(invite.joinLink);
      if (invite.guestPhone && !invite.guestEmail) {
        setNotice(invite.smsSent ? t.room.inviteTexted : t.room.inviteSmsFailed);
      } else if (invite.guestPhone) {
        setNotice(
          invite.emailSent && invite.smsSent
            ? t.room.inviteBothSent
            : invite.emailSent
              ? t.room.inviteSmsFailed
              : t.room.inviteEmailFailed,
        );
      } else {
        setNotice(
          !invite.emailSent
            ? t.room.inviteEmailFailed
            : invite.invitationType === 'salon_friend'
              ? t.room.inviteInApp
              : t.room.inviteEmailed,
        );
      }
    } catch (e: any) {
      setError(e.message ?? t.room.errorGeneric);
    } finally {
      setBusy(false);
    }
  }, [token, sessionId, guestEmail, guestPhone, smsEnabled, t.room]);

  // Guards every exit against running twice. Disconnecting fires the Disconnected event that
  // the effect below also listens on, and unmounting disconnects as well — so without this a
  // normal Leave would report the salon as having ended underneath the user.
  const leaving = useRef(false);

  const handleLeave = useCallback(async () => {
    if (leaving.current) return;
    leaving.current = true;
    setBusy(true);
    try {
      if (roomRef.current) await roomRef.current.disconnect();
      if (token) await endSession(token, sessionId);
    } catch {
      // Leaving must always succeed locally, even if the API call fails.
    } finally {
      onLeft();
    }
  }, [token, sessionId, onLeft]);

  // A salon can end without anybody tapping Leave: the ten-minute cap, or the agent closing a
  // room everybody had left. The API announces it just before deleting the room, so this does
  // not rest on that deletion succeeding — and it used to fail silently, leaving the app in a
  // room with no session behind it and no way to notice.
  useEffect(() => {
    if (!room) return;

    const over = () => {
      if (leaving.current) return;
      leaving.current = true;
      roomRef.current = null;
      room.disconnect().catch(() => {});
      // Deliberately no endSession call: the server is the party that ended it, and asking
      // again answers 409 — an error shown for something that worked.
      onLeft();
    };

    const onData = (
      payload: Uint8Array,
      _participant?: unknown,
      _kind?: unknown,
      topic?: string,
    ) => {
      // Captions travel on their own topic; this message has none.
      if (topic) return;
      try {
        if (JSON.parse(new TextDecoder().decode(payload))?.action === 'session_ended') over();
      } catch {
        // Somebody else's message, or not JSON at all.
      }
    };

    room.on(RoomEvent.DataReceived, onData);
    room.on(RoomEvent.Disconnected, over);
    return () => {
      room.off(RoomEvent.DataReceived, onData);
      room.off(RoomEvent.Disconnected, over);
    };
  }, [room, onLeft]);

  if (connecting) {
    return (
      <View style={styles.centered}>
        <StatusBar style="dark" />
        <ActivityIndicator color={colors.burgundy} />
        <Text style={styles.connectingText}>{t.room.connecting}</Text>
      </View>
    );
  }

  if (driving) {
    return <DrivingMode onExit={() => setDriving(false)} onLeave={handleLeave} />;
  }

  return (
    <KeyboardAvoidingView
      style={styles.flex}
      behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
    >
      {/* Light content on the burgundy bar, as on the site. */}
      <StatusBar style="light" />

      {/* Driving mode returns above this, deliberately: it is a deliberately bare black
          screen, and a burgundy header would defeat the point of it. */}
      <SafeAreaView edges={['top']} style={styles.bar}>
        <Wordmark />
      </SafeAreaView>

      <ScrollView contentContainerStyle={styles.container} keyboardShouldPersistTaps="handled">
        <Text style={styles.title} accessibilityRole="header">
          {t.room.title}
        </Text>

        <View style={styles.micRow}>
          <View style={[styles.micDot, room ? styles.micDotLive : null]} />
          <Text style={styles.micLabel}>
            {room ? t.room.micLive : t.room.micOff}
          </Text>
        </View>

        <Pressable
          style={({ pressed }) => [styles.buttonOutline, pressed && styles.buttonPressed]}
          onPress={() => setDriving(true)}
          accessibilityRole="switch"
          accessibilityState={{ checked: driving }}
          accessibilityLabel={t.room.drivingToggle}
        >
          <Text style={styles.buttonOutlineText}>{t.room.drivingToggle}</Text>
        </Pressable>

        {error ? (
          <Text style={styles.errorText} accessibilityRole="alert" accessibilityLiveRegion="polite">
            {error}
          </Text>
        ) : null}
        {notice ? (
          <Text style={styles.noticeText} accessibilityLiveRegion="polite">{notice}</Text>
        ) : null}

        {/* A Salon starts paused, so this is where one begins. Gold while the agent waits
            and outlined once it is listening: the press that opens a Salon should look like
            the action it is, and stop looking like one afterwards. */}
        <Pressable
          style={({ pressed }) => [
            agentMuted ? styles.buttonGold : styles.buttonOutline,
            agentBusy && styles.buttonDisabled,
            pressed && styles.buttonPressed,
          ]}
          onPress={toggleAgent}
          disabled={agentBusy}
          accessibilityRole="switch"
          accessibilityState={{ checked: !agentMuted, disabled: agentBusy }}
          accessibilityLabel={agentMuted ? t.room.agentActivate : t.room.agentPause}
        >
          <Text style={agentMuted ? styles.buttonGoldText : styles.buttonOutlineText}>
            {agentMuted ? t.room.agentActivate : t.room.agentPause}
          </Text>
        </Pressable>
        <Text style={styles.agentHint}>
          {agentMuted ? t.room.agentHintPaused : t.room.agentHintListening}
        </Text>

        <CaptionsPanel
          captions={captions}
          language={captionLang}
          onLanguageChange={chooseCaptionLang}
        />

        {/* ── Mid-session source (FR3) ── */}
        <Text style={styles.sectionTitle}>{t.room.sourceSection}</Text>
        <TextInput
          style={styles.input}
          value={sourceUrl}
          onChangeText={setSourceUrl}
          placeholder="https://…"
          placeholderTextColor={colors.muted}
          keyboardType="url"
          autoCapitalize="none"
          autoCorrect={false}
          accessibilityLabel={t.room.sourceInputLabel}
          accessibilityHint={t.room.sourceInputHint}
        />
        <Pressable
          style={({ pressed }) => [
            styles.buttonGold,
            (!sourceUrl.trim() || busy) && styles.buttonDisabled,
            pressed && styles.buttonPressed,
          ]}
          onPress={handleAddSource}
          disabled={!sourceUrl.trim() || busy}
          accessibilityRole="button"
          accessibilityLabel={t.room.sourceButton}
        >
          <Text style={styles.buttonGoldText}>{t.room.sourceButton}</Text>
        </Pressable>

        {/* ── Invitation (FR2) ── */}
        <Text style={styles.sectionTitle}>{t.room.inviteSection}</Text>
        <TextInput
          style={styles.input}
          value={guestEmail}
          onChangeText={setGuestEmail}
          placeholder="ami@exemple.com"
          placeholderTextColor={colors.muted}
          keyboardType="email-address"
          autoCapitalize="none"
          autoCorrect={false}
          accessibilityLabel={t.room.inviteInputLabel}
          accessibilityHint={t.room.inviteInputHint}
        />
        {smsEnabled ? (
          <>
            <TextInput
              style={styles.input}
              value={guestPhone}
              onChangeText={setGuestPhone}
              placeholder="+1 514 555 0123"
              placeholderTextColor={colors.muted}
              keyboardType="phone-pad"
              autoCapitalize="none"
              autoCorrect={false}
              accessibilityLabel={t.room.invitePhoneLabel}
              accessibilityHint={t.room.invitePhoneHint}
            />
            <Text style={styles.fieldHint}>{t.room.inviteContactHint}</Text>
          </>
        ) : null}
        <Pressable
          style={({ pressed }) => [styles.buttonOutline, pressed && styles.buttonPressed]}
          onPress={handlePickContact}
          disabled={busy}
          accessibilityRole="button"
          accessibilityLabel={t.room.pickContactButton}
        >
          <Text style={styles.buttonOutlineText}>{t.room.pickContactButton}</Text>
        </Pressable>
        <Pressable
          style={({ pressed }) => [
            styles.buttonGold,
            (!guestEmail.trim() && !(smsEnabled && guestPhone.trim())) || busy
              ? styles.buttonDisabled
              : null,
            pressed && styles.buttonPressed,
          ]}
          onPress={handleInvite}
          disabled={(!guestEmail.trim() && !(smsEnabled && guestPhone.trim())) || busy}
          accessibilityRole="button"
          accessibilityLabel={t.room.inviteButton}
        >
          <Text style={styles.buttonGoldText}>{t.room.inviteButton}</Text>
        </Pressable>
        {joinLink ? <Text style={styles.linkBox} selectable>{joinLink}</Text> : null}

        {/* ── Leave ── */}
        <Pressable
          style={({ pressed }) => [styles.buttonOutline, pressed && styles.buttonPressed]}
          onPress={handleLeave}
          disabled={busy}
          accessibilityRole="button"
          accessibilityLabel={t.room.leaveButton}
        >
          <Text style={styles.buttonOutlineText}>{t.room.leaveButton}</Text>
        </Pressable>
        <PoweredBy />
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1, backgroundColor: colors.ivory },
  // Burgundy behind the inset as well as the bar, so the notch matches the header.
  bar: { backgroundColor: colors.burgundy },
  centered: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.ivory,
    gap: spacing.md,
  },
  connectingText: { fontSize: typography.bodySize, color: colors.charcoal },
  fieldHint: {
    fontSize: typography.captionSize,
    color: colors.muted,
    lineHeight: 19,
    marginTop: spacing.sm,
  },
  container: {
    flexGrow: 1,
    paddingHorizontal: spacing.xl,
    paddingVertical: spacing.xxl,
    backgroundColor: colors.ivory,
  },
  title: {
    fontFamily: typography.titleFamily,
    fontSize: typography.subtitleSize,
    color: colors.burgundy,
    marginBottom: spacing.md,
  },
  micRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm, marginBottom: spacing.lg },
  micDot: { width: 10, height: 10, borderRadius: 5, backgroundColor: colors.muted },
  micDotLive: { backgroundColor: '#2f9e44' },
  micLabel: { fontSize: typography.captionSize, color: colors.muted },
  sectionTitle: {
    fontSize: typography.captionSize,
    color: colors.muted,
    textTransform: 'uppercase',
    letterSpacing: 0.8,
    marginTop: spacing.lg,
    marginBottom: spacing.xs,
  },
  input: {
    minHeight: MIN_TOUCH,
    borderWidth: 1.5,
    borderColor: colors.border,
    borderRadius: 10,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    fontSize: typography.bodySize,
    color: colors.charcoal,
    backgroundColor: colors.white,
    marginBottom: spacing.sm,
  },
  // Under the agent control: what pausing means is not obvious from the word alone.
  agentHint: {
    fontSize: typography.captionSize,
    color: colors.muted,
    marginTop: spacing.xs,
    marginBottom: spacing.sm,
  },
  buttonGold: {
    minHeight: MIN_TOUCH,
    backgroundColor: colors.gold,
    borderRadius: 10,
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: spacing.sm,
  },
  buttonGoldText: { fontSize: typography.bodySize, fontWeight: '600', color: colors.charcoal },
  buttonOutline: {
    minHeight: MIN_TOUCH,
    borderWidth: 1.5,
    borderColor: colors.burgundy,
    borderRadius: 10,
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: spacing.sm,
    marginTop: spacing.xxl,
  },
  buttonOutlineText: { fontSize: typography.bodySize, fontWeight: '600', color: colors.burgundy },
  buttonDisabled: { backgroundColor: colors.muted, opacity: 0.6 },
  buttonPressed: { opacity: 0.75 },
  errorText: { fontSize: typography.captionSize, color: colors.error, marginBottom: spacing.sm },
  noticeText: { fontSize: typography.captionSize, color: colors.burgundy, marginBottom: spacing.sm },
  linkBox: {
    marginTop: spacing.sm,
    padding: spacing.sm,
    borderWidth: 1,
    borderStyle: 'dashed',
    borderColor: colors.gold,
    borderRadius: 8,
    fontSize: typography.captionSize,
    color: colors.charcoal,
    backgroundColor: colors.ivory,
  },
});
