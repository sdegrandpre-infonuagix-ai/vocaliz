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
import { AudioSession } from '@livekit/react-native';
// livekit-client is pulled in by @livekit/react-native, which does not re-export Room;
// it is declared as a direct dependency so this import is not resting on hoisting.
import { Room } from 'livekit-client';

import PoweredBy from '../components/PoweredBy';
import CaptionsPanel from '../components/CaptionsPanel';
import DrivingMode from '../components/DrivingMode';
import { colors, spacing, typography, MIN_TOUCH } from '../theme/tokens';
import { useAuth } from '../contexts/AuthContext';
import { useLanguage } from '../contexts/LanguageContext';
import { useTranslationMute } from '../hooks/useTranslationMute';
import { useCaptions } from '../hooks/useCaptions';
import { addSourceFromUrl, endSession, joinSession, sendHeartbeat } from '../services/sessionsApi';
import { sendInvitation } from '../services/invitationsApi';

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

  const handleInvite = useCallback(async () => {
    if (!token || !guestEmail.trim()) return;
    setBusy(true);
    setNotice(null);
    setJoinLink(null);
    try {
      const invite = await sendInvitation(token, sessionId, guestEmail.trim().toLowerCase());
      setGuestEmail('');
      // The link comes back for every type, and the email goes out for every type. The
      // notice reports what actually happened to the email rather than inferring it from
      // the guest being a member — a member is emailed too, and a send can fail.
      setJoinLink(invite.joinLink);
      setNotice(
        !invite.emailSent
          ? t.room.inviteEmailFailed
          : invite.invitationType === 'salon_friend'
            ? t.room.inviteInApp
            : t.room.inviteEmailed,
      );
    } catch (e: any) {
      setError(e.message ?? t.room.errorGeneric);
    } finally {
      setBusy(false);
    }
  }, [token, sessionId, guestEmail, t.room]);

  const handleLeave = useCallback(async () => {
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
      <StatusBar style="dark" />
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

        <CaptionsPanel
          captions={captions}
          language={captionLang}
          onLanguageChange={setCaptionLang}
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
        <Pressable
          style={({ pressed }) => [
            styles.buttonGold,
            (!guestEmail.trim() || busy) && styles.buttonDisabled,
            pressed && styles.buttonPressed,
          ]}
          onPress={handleInvite}
          disabled={!guestEmail.trim() || busy}
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
  centered: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.ivory,
    gap: spacing.md,
  },
  connectingText: { fontSize: typography.bodySize, color: colors.charcoal },
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
