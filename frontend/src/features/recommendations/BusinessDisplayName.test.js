import React from 'react';
import {render, screen, fireEvent} from '@testing-library/react';
import {businessDisplayName} from './businessDisplayName';
import {ChangeImpactResult} from './ChangeImpactResult';

test.each(['scoped%3Apart%3A42', 'https://example.org/42', 'urn:part:42', 'a'.repeat(64), '<Part/>', '{"name":"part"}'])(
  'does not present technical identity %s as a business name', value => {
    expect(businessDisplayName(value)).toBe('Business name not recorded');
  });

test('retained technical path names are replaced while identity remains inspectable', () => {
  const technical = 'scoped%3Aap242%3Adocument%3A339';
  render(<ChangeImpactResult data={{change_entity:{node_id:'part',name:'Motor'},realization_chain:[{
    node_id:technical,name:technical,path_names:['Motor',technical],path:[{
      relationship_id:'edge',start_id:'part',end_id:technical,relationship_type:'HAS_DOCUMENT'}]}]}}/>);
  expect(screen.getByRole('button',{name:'Inspect Business name not recorded'})).toBeVisible();
  expect(screen.getByText('Motor → Business name not recorded')).toBeVisible();
  const identity = screen.getByText(technical, {selector:'code'});
  expect(identity).not.toBeVisible();
  fireEvent.click(screen.getByText('Record identity'));
  expect(identity).toBeVisible();
});

test('recorded business names and part numbers remain intact', () => {
  expect(businessDisplayName('000687_A_1-INDUCTION MOTOR ASSY 5HP')).toBe('000687_A_1-INDUCTION MOTOR ASSY 5HP');
  expect(businessDisplayName('ISO 10303/AP242')).toBe('ISO 10303/AP242');
});
