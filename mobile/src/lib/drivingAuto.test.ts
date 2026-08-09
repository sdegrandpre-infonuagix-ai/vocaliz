/**
 * The automatism that turns driving mode on by itself.
 *
 * All of it is a pure state machine over speed samples, which is the only way the two
 * thresholds and the delay can be checked at all: the real thing takes two minutes of
 * standing still to make one decision, and no test can wait for that.
 *
 * The speed is computed on the device and never leaves it (FR76). That is not a property of
 * the transport, it is a property of this module — there is nothing here to send, and a test
 * at the bottom of this file fails the build if that stops being true.
 */
import { strict as assert } from 'node:assert';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';

import {
  ENTER_SPEED_KMH,
  EXIT_DELAY_MS,
  EXIT_SPEED_KMH,
  onManualChange,
  onSpeed,
  start,
} from './drivingAuto.ts';

const T0 = 1_000_000;

// ── The switch always works ───────────────────────────────────────────────────

test('the manual switch turns the mode on', () => {
  const state = onManualChange(start(), true, T0);

  assert.equal(state.driving, true);
});

test('the manual switch turns the mode off', () => {
  const on = onManualChange(start(), true, T0);

  assert.equal(onManualChange(on, false, T0).driving, false);
});

test('the manual switch works even once the automatism is suspended', () => {
  // "le contrôle manuel existe toujours" — suspending the automatism must never be a way
  // of losing the switch, or the safety feature has taken away the control it replaced.
  let state = onSpeed(start(), 90, T0);
  state = onManualChange(state, false, T0);
  assert.equal(state.suspended, true);

  state = onManualChange(state, true, T0);

  assert.equal(state.driving, true);
});

// ── Getting in ────────────────────────────────────────────────────────────────

test('moving above the entry speed turns the mode on by itself', () => {
  const state = onSpeed(start(), ENTER_SPEED_KMH + 1, T0);

  assert.equal(state.driving, true);
});

test('the entry threshold is ten kilometres an hour and it must be exceeded', () => {
  assert.equal(ENTER_SPEED_KMH, 10);

  assert.equal(onSpeed(start(), ENTER_SPEED_KMH, T0).driving, false);
});

test('walking pace does not turn it on', () => {
  assert.equal(onSpeed(start(), 4, T0).driving, false);
});

test('a runner or a cyclist does turn it on, and that is the trade accepted', () => {
  // The threshold catches anybody moving. Activating wrongly costs one tap; failing to
  // activate for a driver costs the thing the mode exists to prevent.
  assert.equal(onSpeed(start(), 18, T0).driving, true);
});

// ── Staying in over a red light ───────────────────────────────────────────────

test('stopping at a light does not turn it off', () => {
  const moving = onSpeed(start(), 50, T0);

  const stopped = onSpeed(moving, 0, T0 + 1000);

  assert.equal(stopped.driving, true);
});

test('it takes the whole delay below the exit speed to turn off', () => {
  let state = onSpeed(start(), 50, T0);
  state = onSpeed(state, 0, T0);

  state = onSpeed(state, 0, T0 + EXIT_DELAY_MS - 1);
  assert.equal(state.driving, true);

  state = onSpeed(state, 0, T0 + EXIT_DELAY_MS);
  assert.equal(state.driving, false);
});

test('the exit delay is two minutes', () => {
  assert.equal(EXIT_DELAY_MS, 120_000);
});

test('moving again restarts the delay from nothing', () => {
  // A queue that crawls forward every ninety seconds must never accumulate its way out of
  // the mode. This is why the countdown is a start time and not a running total.
  let state = onSpeed(start(), 50, T0);
  state = onSpeed(state, 0, T0);
  state = onSpeed(state, 30, T0 + EXIT_DELAY_MS - 1);

  state = onSpeed(state, 0, T0 + EXIT_DELAY_MS + 1);

  assert.equal(state.driving, true);
});

test('the two thresholds are different, or the mode would flicker at every junction', () => {
  assert.ok(EXIT_SPEED_KMH < ENTER_SPEED_KMH);
});

test('the exit speed is five kilometres an hour and it must be undercut', () => {
  assert.equal(EXIT_SPEED_KMH, 5);

  let state = onSpeed(start(), 50, T0);
  state = onSpeed(state, EXIT_SPEED_KMH, T0);
  state = onSpeed(state, EXIT_SPEED_KMH, T0 + EXIT_DELAY_MS * 2);

  assert.equal(state.driving, true);
});

test('crawling between the two thresholds keeps the mode on indefinitely', () => {
  // Eight kilometres an hour is under the entry speed and over the exit speed: heavy
  // traffic. The mode stays exactly as it is, which is the point of having two numbers.
  let state = onSpeed(start(), 50, T0);

  state = onSpeed(state, 8, T0 + EXIT_DELAY_MS * 5);

  assert.equal(state.driving, true);
});

// ── Getting out and staying out ───────────────────────────────────────────────

test('leaving by hand while still moving suspends the automatism', () => {
  // The train passenger. Without this, every attempt to leave is undone by the next
  // sample, and they are shut inside a safety feature that was never about them.
  let state = onSpeed(start(), 90, T0);

  state = onManualChange(state, false, T0);

  assert.equal(state.suspended, true);
});

test('a suspended automatism never turns the mode on again', () => {
  let state = onSpeed(start(), 90, T0);
  state = onManualChange(state, false, T0);

  state = onSpeed(state, 300, T0 + 1000);

  assert.equal(state.driving, false);
});

test('the suspension holds for the rest of the Salon', () => {
  let state = onSpeed(start(), 90, T0);
  state = onManualChange(state, false, T0);

  // Stopped for an hour, then moving again — still nothing.
  state = onSpeed(state, 0, T0 + 3_600_000);
  state = onSpeed(state, 120, T0 + 7_200_000);

  assert.equal(state.driving, false);
});

test('leaving by hand while stopped does not suspend anything', () => {
  // They are parked and want their screen back. Nothing about that says they will not be
  // driving again in a minute, so the automatism stays armed.
  let state = onSpeed(start(), 50, T0);
  state = onSpeed(state, 0, T0);

  state = onManualChange(state, false, T0 + 1000);

  assert.equal(state.suspended, false);
});

test('and the automatism arms again when they drive off', () => {
  let state = onSpeed(start(), 50, T0);
  state = onSpeed(state, 0, T0);
  state = onManualChange(state, false, T0 + 1000);

  state = onSpeed(state, 60, T0 + 2000);

  assert.equal(state.driving, true);
});

test('leaving by hand while crawling suspends it too', () => {
  // Six kilometres an hour would not re-activate on its own, but any small acceleration
  // would. Suspending too readily costs an automatism; suspending too late costs the trap.
  let state = onSpeed(start(), 50, T0);

  state = onSpeed(state, 6, T0);
  state = onManualChange(state, false, T0 + 1000);

  assert.equal(state.suspended, true);
});

// ── Whose decision gets undone ────────────────────────────────────────────────

test('the automatism only turns off what it turned on', () => {
  // Somebody who switched the mode on by hand meant it. Standing still for two minutes is
  // not a retraction, and taking it away would be the automatism overruling a person.
  let state = onManualChange(start(), true, T0);

  state = onSpeed(state, 0, T0);
  state = onSpeed(state, 0, T0 + EXIT_DELAY_MS * 2);

  assert.equal(state.driving, true);
});

test('what it turned on, it turns off', () => {
  let state = onSpeed(start(), 50, T0);

  state = onSpeed(state, 0, T0);
  state = onSpeed(state, 0, T0 + EXIT_DELAY_MS);

  assert.equal(state.driving, false);
});

test('switching on by hand during an automatic drive makes the mode the participant\'s', () => {
  // They turned it off, the automatism was suspended, they turned it back on: it is now
  // theirs, and no amount of standing still may take it away.
  let state = onSpeed(start(), 90, T0);
  state = onManualChange(state, false, T0);
  state = onManualChange(state, true, T0 + 1000);

  state = onSpeed(state, 0, T0 + 2000);
  state = onSpeed(state, 0, T0 + 2000 + EXIT_DELAY_MS);

  assert.equal(state.driving, true);
});

// ── Nothing here is telemetry ─────────────────────────────────────────────────

test('the state keeps no position, only a decision', () => {
  // FR76 against FR50. The advertising cell of FR50 is a consented 5.5 km Plus Code; this
  // is an instantaneous speed that never leaves the device. Keeping a coordinate here —
  // even briefly, even unsent — would quietly turn the second into the first.
  let state = onSpeed(start(), 90, T0);
  state = onSpeed(state, 12, T0 + 1000);

  assert.deepEqual(Object.keys(state).sort(), [
    'automatic',
    'driving',
    'moving',
    'slowSince',
    'suspended',
  ]);
  for (const value of Object.values(state)) {
    assert.ok(
      value === null || typeof value === 'boolean' || typeof value === 'number',
      'the state holds decisions and one timestamp, never a reading',
    );
  }
});

test('nothing in this module can reach the network or the disk', () => {
  // The static guard, in the shape the orchestrator uses for conversation content: a
  // reviewer can forget the rule, and a test cannot.
  // Comments are stripped first. A guard that reads prose flags the paragraph explaining
  // the guard, which teaches the next person to word around it rather than to obey it.
  const code = readFileSync(new URL('./drivingAuto.ts', import.meta.url), 'utf8')
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/\/\/.*$/gm, '');

  for (const forbidden of ['fetch', 'XMLHttpRequest', 'SecureStore', 'AsyncStorage', 'import(']) {
    assert.ok(!code.includes(forbidden), `${forbidden} has no business in this module`);
  }
});

test('the module imports nothing at all', () => {
  // Purity is what makes the privacy claim checkable rather than promised. A module with no
  // imports has no transport, no storage and no clock of its own.
  const source = readFileSync(new URL('./drivingAuto.ts', import.meta.url), 'utf8');

  assert.ok(!/^\s*import\s/m.test(source));
});

// ── When there is no position at all ──────────────────────────────────────────

test('a state that is never given a speed simply never decides anything', () => {
  // A browser, or a device whose owner refused the permission. The automatism is
  // unavailable rather than broken: no error, no announcement, and the switch still there.
  const state = start();

  assert.equal(state.driving, false);
  assert.equal(state.suspended, false);
});
