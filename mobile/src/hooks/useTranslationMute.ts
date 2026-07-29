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

interface MuteableRoom {
  on: (event: string, listener: (...args: any[]) => void) => void;
  off: (event: string, listener: (...args: any[]) => void) => void;
  localParticipant: {
    setMicrophoneEnabled: (enabled: boolean) => Promise<void>;
  };
}

export function useTranslationMute(room: MuteableRoom | null | undefined): void {
  useEffect(() => {
    if (!room) return;

    function handleData(payload: Uint8Array): void {
      try {
        const text = new TextDecoder().decode(payload);
        const msg: unknown = JSON.parse(text);
        if (typeof msg !== 'object' || msg === null || !('action' in msg)) return;
        const action = (msg as { action: unknown }).action;
        if (action === 'translation_mute_start') {
          room.localParticipant.setMicrophoneEnabled(false).catch(() => {});
        } else if (action === 'translation_mute_end') {
          room.localParticipant.setMicrophoneEnabled(true).catch(() => {});
        }
      } catch {
        // Ignore malformed messages
      }
    }

    room.on('dataReceived', handleData);
    return () => {
      room.off('dataReceived', handleData);
    };
  }, [room]);
}
