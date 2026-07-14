import assert from 'node:assert/strict';
import test from 'node:test';

import {
  CONNECTION_STATES,
  classifyHealthResult,
  isBackendReachable,
  nextHealthDelayMs,
  shouldTreatChatErrorAsDisconnected,
} from './connectivity.js';

test('classifyHealthResult separates connected, degraded, and disconnected', () => {
  const connected = classifyHealthResult({
    reachable: true,
    state: 'connected',
    health: { status: 'ok' },
  });
  const degraded = classifyHealthResult({
    reachable: true,
    state: 'degraded',
    health: { status: 'degraded', checks: { qdrant: { status: 'unavailable' } } },
    reason: 'degraded',
  });
  const disconnected = classifyHealthResult({
    reachable: false,
    reason: 'health_timeout',
  });

  assert.equal(connected.state, CONNECTION_STATES.CONNECTED);
  assert.equal(degraded.state, CONNECTION_STATES.DEGRADED);
  assert.equal(disconnected.state, CONNECTION_STATES.DISCONNECTED);
  assert.equal(isBackendReachable(degraded), true);
  assert.equal(isBackendReachable(disconnected), false);
});

test('health retry delay is bounded and does not request storm', () => {
  assert.equal(nextHealthDelayMs(CONNECTION_STATES.DISCONNECTED, 0, 'visible'), 1000);
  assert.equal(nextHealthDelayMs(CONNECTION_STATES.DISCONNECTED, 1, 'visible'), 2000);
  assert.equal(nextHealthDelayMs(CONNECTION_STATES.DISCONNECTED, 3, 'visible'), 8000);
  assert.equal(nextHealthDelayMs(CONNECTION_STATES.DISCONNECTED, 99, 'visible'), 12000);
  assert.equal(nextHealthDelayMs(CONNECTION_STATES.CONNECTED, 0, 'visible'), 45000);
  assert.equal(nextHealthDelayMs(CONNECTION_STATES.DEGRADED, 0, 'hidden'), 60000);
});

test('chat HTTP errors prove backend is reachable while network errors do not', () => {
  assert.equal(shouldTreatChatErrorAsDisconnected({ status: 400 }), false);
  assert.equal(shouldTreatChatErrorAsDisconnected({ status: 422 }), false);
  assert.equal(shouldTreatChatErrorAsDisconnected({ status: 429 }), false);
  assert.equal(shouldTreatChatErrorAsDisconnected({ status: 500 }), false);
  assert.equal(shouldTreatChatErrorAsDisconnected({ status: 503 }), false);
  assert.equal(shouldTreatChatErrorAsDisconnected({ status: 504 }), false);
  assert.equal(shouldTreatChatErrorAsDisconnected({ status: null }), true);
  assert.equal(shouldTreatChatErrorAsDisconnected(new TypeError('network down')), true);
});
