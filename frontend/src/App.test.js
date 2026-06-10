import { render, screen } from '@testing-library/react';
import App from './App';

test('renders DEPO platform shell', () => {
  render(<App />);
  expect(screen.getByText(/DEPO Digital Thread Platform/i)).toBeInTheDocument();
});
