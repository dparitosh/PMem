import { describe, it, expect } from 'vitest';
import { importJobState, isResumablePersistedJob, isTerminalPipelineStatus } from './importPresentation';

describe('restored import summary', () => {
  it('resumes a fresh committing job at 100 percent, while keeping approval paused', () => {
    const now = Date.now();
    const status = {status:'ready_for_commit', committing:true, progress:100, lastUpdatedAt:new Date(now).toISOString()};
    expect(isTerminalPipelineStatus(status)).toBe(false);
    expect(isResumablePersistedJob({taskId:'retained-task'}, status, now)).toBe(true);
    expect(isTerminalPipelineStatus({...status, committing:false})).toBe(true);
    expect(isTerminalPipelineStatus({progress:100})).toBe(false);
  });
  it.each([
    [{status:'ready_for_commit',progress:100}, 'awaitingReview'],
    [{status:'ready_for_commit',progress:100,committing:true}, 'active'],
    [{status:'committing',progress:100}, 'active'],
    [{status:'failed',progress:100}, 'failed'],
    [{status:'outcome_unknown',progress:100}, 'failed'],
    [{progress:100}, 'pending'],
    [{status:'completed',progress:100}, 'completed'],
    [{committed:true,progress:100}, 'completed'],
  ])('requires an explicit outcome rather than progress: %j', (status, expected) => {
    expect(importJobState(status)).toBe(expected);
  });
  it('retains failures without a started marker, even at 100 percent', () => {
    expect(importJobState({error:'Conversion exceeds limit',stage:'error',progress:100},false)).toBe('failed');
    expect(importJobState({status:'outcome_unknown'},false)).toBe('failed');
  });
  it('does not mistake restored completed or reviewable jobs for queued jobs', () => {
    expect(importJobState({status:'completed'},false)).toBe('completed');
    expect(importJobState({status:'ready_for_commit',stage:'validate',progress:75},false)).toBe('awaitingReview');
    expect(importJobState({},false)).toBe('pending');
  });
});
