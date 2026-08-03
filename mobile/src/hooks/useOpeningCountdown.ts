/**
 * Counting down to the moment the agent opens the conversation.
 *
 * Started by the guest_invited message the API publishes to the room, not by the response
 * to the invitation request. Two reasons: the agent waits on that same message, so the
 * counter and the agent are driven by one event; and a participant who was already in the
 * room when someone else was invited sees the countdown too.
 *
 * The number of seconds comes from the message. Three codebases each holding their own 15
 * would drift, and the failure would be a counter reaching zero in silence — the most
 * alarming way for this to be wrong.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { Room, RoomEvent } from 'livekit-client';

/** Used only if the message omits the figure — an older API, or something else entirely. */
const FALLBACK_SECONDS = 15;

export function useOpeningCountdown(room: Room | null) {
  // null means no countdown is running and nothing should be shown. Zero is a real state:
  // the agent is starting, and that is worth saying.
  const [secondsLeft, setSecondsLeft] = useState<number | null>(null);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  const stop = useCallback(() => {
    if (timer.current) {
      clearInterval(timer.current);
      timer.current = null;
    }
  }, []);

  const start = useCallback(
    (seconds: number) => {
      stop();
      setSecondsLeft(seconds);
      timer.current = setInterval(() => {
        setSecondsLeft((left) => {
          if (left === null) return null;
          const next = left - 1;
          if (next <= 0) {
            stop();
            // Left at zero rather than cleared: the last thing anyone read should be that
            // the agent is starting, not a panel that vanished a moment before it spoke.
            return 0;
          }
          return next;
        });
      }, 1000);
    },
    [stop],
  );

  useEffect(() => {
    if (!room) return;

    const onData = (
      payload: Uint8Array,
      _participant?: unknown,
      _kind?: unknown,
      topic?: string,
    ) => {
      // Captions travel on their own topic; this message has none.
      if (topic) return;
      let message: any;
      try {
        message = JSON.parse(new TextDecoder().decode(payload));
      } catch {
        return;
      }
      if (message?.action !== 'guest_invited') return;
      const seconds = Number(message.opensInSeconds);
      start(Number.isFinite(seconds) && seconds > 0 ? seconds : FALLBACK_SECONDS);
    };

    room.on(RoomEvent.DataReceived, onData);
    return () => {
      room.off(RoomEvent.DataReceived, onData);
      stop();
    };
  }, [room, start, stop]);

  return secondsLeft;
}
