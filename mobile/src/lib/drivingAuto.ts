/**
 * FR76 — turning driving mode on without being asked to think about it.
 *
 * A pure state machine over speed samples. It imports nothing, holds no position, and has
 * no clock of its own: every decision is a function of the samples it is given and the time
 * it is told. That is what makes the privacy claim checkable instead of promised — there is
 * nothing in this file that *could* send a reading anywhere, and `drivingAuto.test.ts`
 * fails the build if an import, a `fetch` or a store ever appears.
 *
 * The distinction from FR50 matters and is not a matter of degree. FR50 collects a 5.5 km
 * Plus Code cell, with explicit consent, in order to target advertising. This reads an
 * instantaneous speed that never leaves the device and is never written down. Refusing one
 * says nothing about the other, and consenting to FR50 is not permission for this.
 */

/** Above this, the mode turns itself on. Exceeded, not merely reached. */
export const ENTER_SPEED_KMH = 10;

/**
 * Below this — undercut, not merely reached — the countdown out of the mode runs.
 *
 * Two numbers rather than one, because a single threshold would drop the mode at every red
 * light and pick it up again at every green one. The gap between 5 and 10 is where a car in
 * heavy traffic lives, and inside it nothing changes in either direction.
 */
export const EXIT_SPEED_KMH = 5;

/** How long the speed must stay under `EXIT_SPEED_KMH` before the mode gives up on driving. */
export const EXIT_DELAY_MS = 120_000;

export type DrivingAuto = {
  /** Whether the mode is on. */
  driving: boolean;
  /**
   * Whether the automatism is what turned it on. It only ever undoes its own decisions: a
   * participant who reached for the switch meant it, and standing still is not a retraction.
   */
  automatic: boolean;
  /**
   * Set when somebody leaves the mode by hand while still moving, and never cleared.
   *
   * This is the train passenger. Without it, every attempt to leave is undone by the next
   * sample a second later, and they are shut inside a safety feature that was never about
   * them. The switch keeps working while this holds — the automatism is suspended, not the
   * control.
   */
  suspended: boolean;
  /** Whether the last sample was above `EXIT_SPEED_KMH`. A decision, not a reading. */
  moving: boolean;
  /** When the speed first fell below `EXIT_SPEED_KMH`, or `null` if it has not. */
  slowSince: number | null;
};

export function start(): DrivingAuto {
  return { driving: false, automatic: false, suspended: false, moving: false, slowSince: null };
}

/**
 * Take one speed reading, in kilometres an hour, and decide what it means.
 *
 * The countdown out of the mode is stored as the moment it began rather than as a running
 * total, so a queue that crawls forward every ninety seconds can never accumulate its way
 * out: any movement above the exit speed puts it back to nothing.
 */
export function onSpeed(state: DrivingAuto, speedKmh: number, now: number): DrivingAuto {
  // Under the exit speed, not merely at it: the countdown asks the participant to be
  // *below* 5 km/h, so exactly 5 still counts as moving.
  const moving = speedKmh >= EXIT_SPEED_KMH;
  if (state.suspended) {
    return { ...state, moving };
  }

  if (!state.driving) {
    return speedKmh > ENTER_SPEED_KMH
      ? { ...state, driving: true, automatic: true, moving, slowSince: null }
      : { ...state, moving, slowSince: null };
  }

  if (moving) {
    return { ...state, moving, slowSince: null };
  }

  // Only the automatism's own drive can end this way.
  if (!state.automatic) {
    return { ...state, moving, slowSince: null };
  }

  const slowSince = state.slowSince ?? now;
  if (now - slowSince >= EXIT_DELAY_MS) {
    return { ...state, driving: false, automatic: false, moving, slowSince: null };
  }
  return { ...state, moving, slowSince };
}

/**
 * Record the participant working the switch, which is available in every circumstance.
 *
 * Leaving while still moving suspends the automatism. "Still moving" is measured against the
 * *exit* speed rather than the entry speed, which suspends more readily than the trap
 * strictly requires: at 6 km/h nothing would re-activate on its own, but the smallest
 * acceleration would. The asymmetry is deliberate — suspending too eagerly costs an
 * automatism the participant can live without, and suspending too late costs them the black
 * screen they just asked to leave.
 */
export function onManualChange(state: DrivingAuto, driving: boolean, now: number): DrivingAuto {
  if (driving) {
    // Theirs now, whatever it was before, so the automatism will not take it back.
    return { ...state, driving: true, automatic: false, slowSince: null };
  }
  return {
    ...state,
    driving: false,
    automatic: false,
    suspended: state.suspended || state.moving,
    slowSince: null,
  };
}
