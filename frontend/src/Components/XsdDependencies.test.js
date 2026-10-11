import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { appendXsdDependencies } from './XsdDependencies';
import XsdDependencies from './XsdDependencies';
import { vi } from 'vitest';

test('companion bundle sends files and relative paths in matching order', () => {
  const form = new FormData();
  const files = [new File(['common'], 'common.xsd'), new File(['types'], 'types.xsd')];
  appendXsdDependencies(form, new File(['root'], 'bom.xsd'), files, 'common.xsd\nshared/types.xsd');
  expect(form.getAll('dependencies').map(file => file.name)).toEqual(['common.xsd', 'types.xsd']);
  expect(JSON.parse(form.get('dependency_paths'))).toEqual(['common.xsd', 'shared/types.xsd']);
});

test.each(['../common.xsd', 'C:/common.xsd', 'bom.xsd', '/common.xsd', 'folder\\common.xsd'])('unsafe or colliding companion path %s is rejected', path => {
  expect(() => appendXsdDependencies(new FormData(), new File(['root'], 'bom.xsd'), [new File(['common'], 'common.xsd')], path)).toThrow(/Companion paths/);
});

test('path count must match companion file count', () => {
  expect(() => appendXsdDependencies(new FormData(), new File(['root'], 'bom.xsd'), [new File(['common'], 'common.xsd')], '')).toThrow(/one relative path/);
});

test('selection supplies default paths and allows clearing', () => {
  const onChange = vi.fn();
  const files = [new File(['common'], 'common.xsd')];
  const view = render(<XsdDependencies files={[]} paths="" onChange={onChange} />);
  fireEvent.change(screen.getByLabelText('Companion XSD files'), { target: { files } });
  expect(onChange).toHaveBeenCalledWith(files, 'common.xsd');
  view.rerender(<XsdDependencies files={files} paths="common.xsd" onChange={onChange} />);
  fireEvent.click(screen.getByRole('button', { name: 'Clear companion files' }));
  expect(onChange).toHaveBeenLastCalledWith([], '');
});
