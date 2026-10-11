import { expect, test } from 'vitest';
import { telemetryCategories } from './ReportsAnalytics';

test('status categories include new counters without inventing missing statuses', () => {
  expect(telemetryCategories({ paused_runs: 3, cancelled_runs: 2, total_runs: 5 }, 'runs'))
    .toEqual([{ name: 'paused', count: 3 }, { name: 'cancelled', count: 2 }]);
});

test('missing and invalid telemetry counters are not displayed as zero', () => {
  expect(telemetryCategories({ failed_runs: null, queued_runs: '2', running_runs: NaN }, 'runs')).toEqual([]);
});

test('record categories come from the service without fixed accepted/rejected categories', () => {
  expect(telemetryCategories({ records_quarantined: 4, records_validated: 10 }, 'quality'))
    .toEqual([{ name: 'quarantined', count: 4 }, { name: 'validated', count: 10 }]);
});
