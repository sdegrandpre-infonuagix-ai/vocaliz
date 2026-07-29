/**
 * Session creation screen — host enters a URL or uploads a document to start a session (FR1).
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

import { colors, spacing, typography, MIN_TOUCH } from '../theme/tokens';
import { useAuth } from '../contexts/AuthContext';
import { createSessionFromUrl } from '../services/sessionsApi';

interface Props {
  onSessionCreated?: (sessionId: string, roomName: string, hostToken: string) => void;
}

export default function SessionCreationScreen({ onSessionCreated }: Props) {
  const [sourceUrl, setSourceUrl] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { token } = useAuth();

  const isValidUrl = /^https?:\/\/.+/.test(sourceUrl.trim());

  async function handleCreate() {
    if (!token || !isValidUrl) return;
    setIsLoading(true);
    setError(null);
    try {
      const session = await createSessionFromUrl(token, sourceUrl.trim());
      onSessionCreated?.(session.sessionId, session.livekitRoomName, session.hostToken);
    } catch (e: any) {
      setError(e.message ?? 'Impossible de créer la session.');
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <KeyboardAvoidingView
      style={styles.flex}
      behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
    >
      <StatusBar style="dark" />
      <ScrollView
        contentContainerStyle={styles.container}
        keyboardShouldPersistTaps="handled"
      >
        {/* ── Header ── */}
        <Text style={styles.title} accessibilityRole="header">
          Nouvelle session
        </Text>
        <Text style={styles.subtitle}>
          Partagez une URL d'article pour démarrer une discussion guidée par l'agent.
        </Text>

        {/* ── URL input ── */}
        <Text style={styles.label} accessibilityElementsHidden>
          URL de l'article
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
          accessibilityLabel="URL de l'article source"
          accessibilityHint="Entrez l'adresse web de l'article à discuter"
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
          accessibilityLabel="Démarrer la session"
          accessibilityState={{ disabled: !isValidUrl || isLoading, busy: isLoading }}
        >
          {isLoading ? (
            <ActivityIndicator color={colors.ivory} />
          ) : (
            <Text style={styles.buttonText}>Démarrer la session</Text>
          )}
        </Pressable>

        {/* ── Divider ── */}
        <View style={styles.dividerRow} accessibilityElementsHidden>
          <View style={styles.dividerLine} />
          <Text style={styles.dividerText}>ou</Text>
          <View style={styles.dividerLine} />
        </View>

        {/* ── Document upload placeholder (file picker added with expo-document-picker in Story 2.3) ── */}
        <Pressable
          style={styles.uploadButton}
          onPress={() => Alert.alert('Prochainement', 'Le téléversement de documents sera disponible dans la prochaine mise à jour.')}
          accessibilityRole="button"
          accessibilityLabel="Téléverser un document"
          accessibilityHint="Sélectionnez un fichier PDF ou texte"
        >
          <Text style={styles.uploadButtonText}>📄  Téléverser un document</Text>
        </Pressable>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1, backgroundColor: colors.ivory },
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
});
