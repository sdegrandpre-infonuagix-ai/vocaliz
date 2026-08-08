/**
 * Driving mode: the Salon with nothing to look at.
 *
 * A black screen over everything, the conversation carrying on underneath. The point is
 * not to hide the interface — it is to remove the reason to glance at it. Captions, the
 * source field and the invitation form all invite a look down; none of them belong in a
 * car.
 *
 * Two consequences follow, and both are deliberate:
 *
 * The screen is kept awake. A phone that locks after thirty seconds would need waking,
 * unlocking and finding the app again to leave the mode — precisely the fumbling this is
 * meant to prevent. useKeepAwake releases the lock when this component unmounts, so the
 * phone goes back to normal the moment driving mode ends.
 *
 * The caption language is cleared while it is on. Nobody is reading, so nothing needs
 * translating: the agent sees the attribute empty and stops paying to render turns this
 * participant will never see. The previous choice is restored on the way out.
 */
import React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { StatusBar } from 'expo-status-bar';
import { useKeepAwake } from 'expo-keep-awake';

import { useLanguage } from '../contexts/LanguageContext';

interface Props {
  /** Called when the driver taps to come back. */
  onExit: () => void;
  /** Ends the salon outright, without leaving driving mode first. */
  onLeave: () => void;
}

export default function DrivingMode({ onExit, onLeave }: Props) {
  // Held for exactly as long as this overlay is mounted.
  useKeepAwake();
  const { t } = useLanguage();

  return (
    <View style={styles.screen}>
      {/* Light text on black, so the status bar does not glow white in a dark car. */}
      <StatusBar style="light" />

      {/* The whole screen is the exit. A driver should not have to find a button, and
          the one thing they might do by feel is tap the glass. */}
      <Pressable
        style={styles.exitArea}
        onPress={onExit}
        accessibilityRole="button"
        accessibilityLabel={t.room.drivingExit}
      >
        <Text style={styles.hint}>{t.room.drivingHint}</Text>
      </Pressable>

      {/* Leaving is the one action worth its own target: ending a call must not require
          two steps, and it sits at the bottom where a thumb rests rather than where a
          stray tap lands. */}
      <Pressable
        style={styles.leave}
        onPress={onLeave}
        accessibilityRole="button"
        accessibilityLabel={t.room.leaveButton}
      >
        <Text style={styles.leaveText}>{t.room.leaveButton}</Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  // Fills the screen outright rather than sitting in the layout: driving mode replaces
  // the room, it does not sit above part of it.
  screen: { flex: 1, backgroundColor: '#000' },
  exitArea: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: 24 },
  // Dim on purpose: bright enough to find in the dark, too dim to draw the eye.
  hint: { color: '#5A5A5A', fontSize: 15, textAlign: 'center', lineHeight: 22 },
  leave: {
    minHeight: 64,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 36,
    marginHorizontal: 24,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: '#3A3A3A',
  },
  leaveText: { color: '#9A9A9A', fontSize: 17, fontWeight: '600' },
});
