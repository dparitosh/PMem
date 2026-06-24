import { render, screen } from '@testing-library/react';
import App from './App';
jest.mock('./SchemaContext', () => ({
  SchemaProvider: ({ children }) => children,
}));

jest.mock('./contexts/OntologyContext', () => ({
  OntologyProvider: ({ children }) => children,
}));

jest.mock('./Components/LandingPage', () => () => <div>Landing Mock</div>);

test('renders DEPO platform shell', () => {
  render(<App />);
  expect(screen.getByText(/DEPO Digital Thread Platform/i)).toBeInTheDocument();
});
