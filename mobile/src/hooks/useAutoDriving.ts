/**
 * FR76 — driving mode turning itself on, and the location plumbing that feeds it.
 *
 * Every decision lives in `../lib/drivingAuto`, which is pure and knows nothing about
 * phones. This file is only the part that cannot be tested without a device: asking for the
 * permission, watching the position, and converting metres a second into kilometres an hour.
 *
 * The speed is read here and used here. It is not stored, not put in state, and not sent
 * anywhere — the only thing that leaves this hook is a boolean about the screen. That is
 * what separates FR76 from FR50's advertising cell, which is coarse, consented to
 * separately, and deliberately unrelated to this.
 */
import { useCallback, useEffect, useRef, useState } from 'react';

import {
  DrivingAuto,
  onManualChange,
  onSpeed,
  start,
} from '../lib/drivingAuto';

/**
 * Metres a second to kilometres an hour.
 *
 * The platforms report `null` when they have no fix, and negative values when the reading
 * is meaningless. Both mean "no speed", which is not the same as "stopped" — treating them
 * as zero would start the countdown out of the mode every time the signal dropped.
 */
function kmh(metresPerSecond: number | null | undefined): number | null {
  if (metresPerSecond == null || metresPerSecond < 0) return null;
  return metresPerSecond * 3.6;
}

export type AutoDriving = {
  /** Whether the black screen is up. */
  driving: boolean;
  /** The switch, which works in every circumstance, permission or no permission. */
  setDriving: (on: boolean) => void;
  /** Whether the participant has asked for the automatism. */
  automatic: boolean;
  /**
   * Ask for it, or give it up. Turning it on is the moment the permission is requested —
   * never at install, and never on joining a Salon.
   */
  setAutomatic: (on: boolean) => Promise<void>;
  /**
   * `false` on a browser, on a device without a position, or after a refusal. Nothing is
   * announced when it is false: the automatism is unavailable, the switch still works, and
   * there is no degradation to report to somebody who never asked for the feature.
   */
  available: boolean;
};

export function useAutoDriving(): AutoDriving {
  const [state, setState] = useState<DrivingAuto>(start);
  const [automatic, setAutomaticState] = useState(false);
  const [available, setAvailable] = useState(true);
  const watcher = useRef<{ remove: () => void } | null>(null);

  const setDriving = useCallback((on: boolean) => {
    setState((current) => onManualChange(current, on, Date.now()));
  }, []);

  const setAutomatic = useCallback(async (on: boolean) => {
    if (!on) {
      setAutomaticState(false);
      return;
    }

    let Location;
    try {
      Location = await import('expo-location');
    } catch {
      // No location module at all — a browser, or a build without it.
      setAvailable(false);
      return;
    }

    // Asked for here, at the moment the automatism is switched on, so the request arrives
    // with a reason attached rather than as one of a list of permissions at install.
    const { granted } = await Location.requestForegroundPermissionsAsync();
    if (!granted) {
      // A refusal is an answer, not a fault. The switch is untouched and nothing is said.
      setAvailable(false);
      return;
    }

    setAvailable(true);
    setAutomaticState(true);
  }, []);

  useEffect(() => {
    if (!automatic) {
      watcher.current?.remove();
      watcher.current = null;
      return;
    }

    let cancelled = false;
    (async () => {
      const Location = await import('expo-location');
      const subscription = await Location.watchPositionAsync(
        {
          // The lowest accuracy that can still tell 5 from 10 km/h. Continuous
          // high-precision tracking would spend a journey's worth of battery on a decision
          // that is one bit wide.
          accuracy: Location.Accuracy.Balanced,
          timeInterval: 5000,
          distanceInterval: 10,
        },
        ({ coords }) => {
          const speed = kmh(coords.speed);
          if (speed == null) return;
          setState((current) => onSpeed(current, speed, Date.now()));
        },
        () => {
          // Reported by the platform after the watch is running — the location services
          // switched off mid-journey, say. Give the automatism up rather than sit on a
          // subscription that will never speak again; the switch is unaffected.
          setAvailable(false);
          setAutomaticState(false);
        },
      );
      if (cancelled) subscription.remove();
      else watcher.current = subscription;
    })().catch(() => {
      // Watching failed after the permission was granted — a device without a working
      // sensor. Same outcome as never having had one.
      setAvailable(false);
      setAutomaticState(false);
    });

    return () => {
      cancelled = true;
      watcher.current?.remove();
      watcher.current = null;
    };
  }, [automatic]);

  return { driving: state.driving, setDriving, automatic, setAutomatic, available };
}
