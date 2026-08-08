/**
 * Salon creation screen — host enters a URL or uploads a document to start a salon (FR1).
 * Palette: Salon Parisien. WCAG AA touch targets and ARIA labels.
 */
import React, { useState } from 'react';
import {
  ActivityIndicator,
  Alert,
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

import PoweredBy from '../components/PoweredBy';
import LanguageToggle from '../components/LanguageToggle';
import Wordmark from '../components/Wordmark';
import { colors, spacing, typography, MIN_TOUCH } from '../theme/tokens';
import { useAuth } from '../contexts/AuthContext';
import { useLanguage } from '../contexts/LanguageContext';
import { createSalonFromUrl, createSalonWithoutSource } from '../services/salonsApi';

interface Props {
  onSalonCreated?: (salonId: string, roomName: string, hostToken: string) => void;
}

export default function SalonCreationScreen({ onSalonCreated }: Props) {
  const [sourceUrl, setSourceUrl] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { token } = useAuth();
  const { t } = useLanguage();

  const isValidUrl = /^https?:\/\/.+/.test(sourceUrl.trim());

  /** Creates the salon, then hands it to the caller. `create` chooses the source mode. */
  async function runCreate(create: () => Promise<Awaited<ReturnType<typeof createSalonFromUrl>>>) {
    if (!token) return;
    setIsLoading(true);
    setError(null);
    try {
      const salon = await create();
      onSalonCreated?.(salon.salonId, salon.livekitRoomName, salon.hostToken);
    } catch (e: any) {
      setError(e.message ?? t.salon.errorGeneric);
    } finally {
      setIsLoading(false);
    }
  }

  function handleCreate() {
    if (!isValidUrl) return;
    return runCreate(() => createSalonFromUrl(token!, sourceUrl.trim()));
  }

  // No document, no URL — the agent opens by asking what to discuss.
  function handleCreateWithoutSource() {
    return runCreate(() => createSalonWithoutSource(token!));
  }

  return (
    <KeyboardAvoidingView
      style={styles.flex}
      behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
    >
      {/* Light content on the burgundy bar, as on the site. */}
      <StatusBar style="light" />

      {/* Outside the ScrollView so the bar reaches both edges and stays put under the
          keyboard, exactly as the site's header does not scroll away. */}
      <SafeAreaView edges={['top']} style={styles.bar}>
        <Wordmark />
      </SafeAreaView>

      <ScrollView
        contentContainerStyle={styles.container}
        keyboardShouldPersistTaps="handled"
      >
        {/* ── Language switch ──
            Repeated here because this is the first screen after signing in, and the
            switch on the email screen is no longer reachable once a token is held. */}
        <LanguageToggle />

        {/* ── Header ── */}
        <Text style={styles.title} accessibilityRole="header">
          {t.salon.title}
        </Text>
        {/* What the platform is. Repeated here because a host who signed in on a previous
            run never passes the entry screen again. */}
        <Text style={styles.whatIs}>{t.whatIsVocaliz}</Text>

        <Text style={styles.subtitle}>
          {t.salon.subtitle}
        </Text>

        {/* ── URL input ── */}
        <Text style={styles.label} accessibilityElementsHidden>
          {t.salon.urlLabel}
        </Text>
        <TextInput
          style={[styles.input, error ? styles.inputError : null]}
          value={sourceUrl}
          onChangeText={text => { setSourceUrl(text); setError(null); }}
          placeholder="https://www.lemonde.fr/article…"
          placeholderTextColor={colors.muted}
          keyboardType="url"
          autoCapitalize="none"
          autoCorrect={false}
          textContentType="URL"
          accessibilityLabel={t.salon.urlInputLabel}
          accessibilityHint={t.salon.urlInputHint}
        />

        {/* ── Error ── */}
        {error ? (
          <Text style={styles.errorText} accessibilityRole="alert" accessibilityLiveRegion="polite">
            {error}
          </Text>
        ) : null}

        {/* ── CTA ── */}
        <Pressable
          style={({ pressed }) => [
            styles.button,
            (!isValidUrl || isLoading) && styles.buttonDisabled,
            pressed && isValidUrl && !isLoading && styles.buttonPressed,
          ]}
          onPress={handleCreate}
          disabled={!isValidUrl || isLoading}
          accessibilityRole="button"
          accessibilityLabel={t.salon.startButton}
          accessibilityState={{ disabled: !isValidUrl || isLoading, busy: isLoading }}
        >
          {isLoading ? (
            <ActivityIndicator color={colors.ivory} />
          ) : (
            <Text style={styles.buttonText}>{t.salon.startButton}</Text>
          )}
        </Pressable>

        {/* ── Divider ── */}
        <View style={styles.dividerRow} accessibilityElementsHidden>
          <View style={styles.dividerLine} />
          <Text style={styles.dividerText}>{t.salon.or}</Text>
          <View style={styles.dividerLine} />
        </View>

        {/* ── Document upload placeholder (file picker added with expo-document-picker in Story 2.3) ── */}
        <Pressable
          style={styles.uploadButton}
          onPress={() => Alert.alert(t.salon.uploadComingSoonTitle, t.salon.uploadComingSoonMsg)}
          accessibilityRole="button"
          accessibilityLabel={t.salon.uploadButtonLabel}
          accessibilityHint={t.salon.uploadButtonHint}
        >
          <Text style={styles.uploadButtonText}>{t.salon.uploadButton}</Text>
        </Pressable>

        {/* ── Source-less salon: the agent asks what to discuss ── */}
        <Pressable
          style={({ pressed }) => [
            styles.noSourceButton,
            isLoading && styles.noSourceButtonDisabled,
            pressed && !isLoading && styles.noSourceButtonPressed,
          ]}
          onPress={handleCreateWithoutSource}
          disabled={isLoading}
          accessibilityRole="button"
          accessibilityLabel={t.salon.noSourceButtonLabel}
          accessibilityHint={t.salon.noSourceButtonHint}
          accessibilityState={{ disabled: isLoading, busy: isLoading }}
        >
          <Text style={styles.noSourceButtonText}>{t.salon.noSourceButton}</Text>
        </Pressable>
        <PoweredBy />
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1, backgroundColor: colors.ivory },
  // Burgundy behind the inset as well as the bar, so the notch area matches the header
  // instead of showing ivory above it.
  bar: { backgroundColor: colors.burgundy },
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
    marginBottom: spacing.sm,
  },
  // The one sentence a first-time reader needs. Muted so it orients without competing with
  // the action the screen is for.
  whatIs: {
    fontSize: typography.captionSize,
    color: colors.muted,
    textAlign: 'center',
    lineHeight: typography.captionSize * 1.5,
    marginBottom: spacing.md,
  },
  subtitle: {
    fontSize: typography.bodySize,
    color: colors.charcoal,
    lineHeight: typography.bodySize * 1.5,
    marginBottom: spacing.xl,
  },
  label: {
    fontSize: typography.captionSize,
    color: colors.muted,
    marginBottom: spacing.xs,
    textTransform: 'uppercase',
    letterSpacing: 0.8,
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
    marginBottom: spacing.md,
  },
  inputError: { borderColor: colors.error },
  errorText: {
    fontSize: typography.captionSize,
    color: colors.error,
    marginBottom: spacing.md,
  },
  button: {
    minHeight: MIN_TOUCH,
    backgroundColor: colors.burgundy,
    borderRadius: 10,
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: spacing.sm,
    marginBottom: spacing.xl,
  },
  buttonDisabled: { backgroundColor: colors.muted, opacity: 0.6 },
  buttonPressed: { backgroundColor: colors.burgundyDark },
  buttonText: {
    fontSize: typography.bodySize,
    fontWeight: '600',
    color: colors.ivory,
    letterSpacing: 0.5,
  },
  dividerRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: spacing.xl,
  },
  dividerLine: { flex: 1, height: 1, backgroundColor: colors.border },
  dividerText: {
    fontSize: typography.captionSize,
    color: colors.muted,
    marginHorizontal: spacing.md,
  },
  uploadButton: {
    minHeight: MIN_TOUCH,
    borderWidth: 1.5,
    borderColor: colors.gold,
    borderRadius: 10,
    borderStyle: 'dashed',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: spacing.sm,
  },
  uploadButtonText: {
    fontSize: typography.bodySize,
    color: colors.gold,
    fontWeight: '600',
  },
  noSourceButton: {
    minHeight: MIN_TOUCH,
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: spacing.sm,
    marginTop: spacing.lg,
  },
  noSourceButtonDisabled: { opacity: 0.5 },
  noSourceButtonPressed: { opacity: 0.7 },
  noSourceButtonText: {
    fontSize: typography.bodySize,
    color: colors.burgundy,
    fontWeight: '600',
    textDecorationLine: 'underline',
  },
});
