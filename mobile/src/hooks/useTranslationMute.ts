/**
 * Listens for translation control data messages from the Salon agent and
 * temporarily mutes the local microphone to prevent echo while the agent
 * reads a translation aloud (Story 2.10).
 *
 * Protocol:
 *   Agent → room: {"action": "translation_mute_start"}  — mute local mic
 *   Agent → room: {"action": "translation_mute_end"}    — unmute local mic
 *
 * Usage: call this hook inside any component that has a live LiveKit room.
 *   const room = ...; // Room instance from @livekit/react-native
 *   useTranslationMute(room);
 */
import { useEffect } from 'react';

/**
 * Structurally what this hook needs. Kept deliberately loose rather than importing
 * livekit-client's Room: its event signatures are heavily overloaded generics that a
 * plain string literal cannot satisfy, and tests stub the room entirely.
 */
export interface MuteableRoom {
  on: (event: any, listener: any) => any;
  off: (event: any, listener: any) => any;
  localParticipant: {
    setMicrophoneEnabled: (enabled: boolean) => Promise<unknown>;
  };
}

export function useTranslationMute(room: MuteableRoom | null | undefined): void {
  useEffect(() => {
    if (!room) return;
    // Captured so the closures below keep a non-null reference TypeScript can narrow.
    const live = room;

    function handleData(payload: Uint8Array): void {
      try {
        const text = new TextDecoder().decode(payload);
        const msg: unknown = JSON.parse(text);
        if (typeof msg !== 'object' || msg === null || !('action' in msg)) return;
        const action = (msg as { action: unknown }).action;
        if (action === 'translation_mute_start') {
          live.localParticipant.setMicrophoneEnabled(false).catch(() => {});
        } else if (action === 'translation_mute_end') {
          live.localParticipant.setMicrophoneEnabled(true).catch(() => {});
        }
      } catch {
        // Ignore malformed messages
      }
    }

    live.on('dataReceived', handleData);
    return () => {
      live.off('dataReceived', handleData);
    };
  }, [room]);
}
