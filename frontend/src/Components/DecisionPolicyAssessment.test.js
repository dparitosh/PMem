import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import DecisionPolicyAssessment from './DecisionPolicyAssessment';

describe('Shared decision policy evidence', () => {
  it('distinguishes no configured policy from approval', () => {
    render(<DecisionPolicyAssessment report={{status:'not_configured'}} />);
    expect(screen.getByText(/No shared decision policy is configured/)).toBeInTheDocument();
  });
  it('explains a hold and the violated native rule', () => {
    render(<DecisionPolicyAssessment report={{status:'blocked',checks:[{policy_id:'minimum',compliant:false,violations:['Confidence too low: 0.6']}]}} />);
    expect(screen.getByText(/Decision policy holds/)).toBeInTheDocument();
    expect(screen.getByText('Confidence too low: 0.6')).toBeInTheDocument();
  });
  it('does not mistake an unavailable evaluator for no configured policy', () => {
    render(<DecisionPolicyAssessment report={{status:'unavailable'}} />);
    expect(screen.getByText(/Publication is held/)).toBeInTheDocument();
  });
});
