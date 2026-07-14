import assert from 'node:assert/strict';
import test from 'node:test';

import {
  responseBadgeLabel,
  sourceDisplayLabels,
} from './presentationMetadata.js';

test('sourceDisplayLabels prefers friendly metadata and hides raw technical ids', () => {
  const labels = sourceDisplayLabels({
    sources: ['entity:active_ingredient', 'web_raw_dataset.json'],
    source_metadata: [
      {
        source_id: 'entity:active_ingredient',
        display_name: 'Cơ sở tri thức hoạt chất',
      },
      {
        source_id: 'web_raw_dataset.json',
        display_name: 'Bộ dữ liệu kiến thức mụn',
      },
    ],
  });

  assert.deepEqual(labels, ['Cơ sở tri thức hoạt chất', 'Bộ dữ liệu kiến thức mụn']);
  assert.equal(labels.some((label) => label.startsWith('entity:')), false);
  assert.equal(labels.includes('web_raw_dataset.json'), false);
});

test('responseBadgeLabel does not show Guardrail for system deterministic routine answer', () => {
  const label = responseBadgeLabel({
    provider: 'system',
    model: null,
    response_origin: 'deterministic',
    guardrail_applied: false,
    guardrail: 'in_domain',
  });

  assert.equal(label, '🧭 Hướng dẫn an toàn');
  assert.equal(label.includes('Guardrail'), false);
});

test('responseBadgeLabel only shows Guardrail for real guardrail intervention', () => {
  const label = responseBadgeLabel({
    provider: 'system',
    model: 'guardrail-rule',
    response_origin: 'guardrail',
    guardrail_applied: true,
    guardrail: 'out_of_domain',
  });

  assert.equal(label, '🛡️ Guardrail');
});
