import { describe, it, expect } from 'vitest';
import { importJobState } from './importPresentation';

describe('restored import summary', () => {
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
