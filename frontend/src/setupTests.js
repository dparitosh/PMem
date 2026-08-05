// jest-dom adds custom jest matchers for asserting on DOM nodes.
// allows you to do things like:
// expect(element).toHaveTextContent(/react/i)
// learn more: https://github.com/testing-library/jest-dom
import '@testing-library/jest-dom';

const mockAxios = {
  get: jest.fn(() => Promise.resolve({ data: {} })),
  post: jest.fn(() => Promise.resolve({ data: {} })),
  put: jest.fn(() => Promise.resolve({ data: {} })),
  patch: jest.fn(() => Promise.resolve({ data: {} })),
  delete: jest.fn(() => Promise.resolve({ data: {} })),
  request: jest.fn(() => Promise.resolve({ data: {} })),
  interceptors: {
    request: { use: jest.fn() },
    response: { use: jest.fn() },
  },
};

jest.mock('axios', () => ({
  __esModule: true,
  default: {
    ...mockAxios,
    create: jest.fn(() => mockAxios),
    isAxiosError: jest.fn(() => false),
  },
  ...mockAxios,
  create: jest.fn(() => mockAxios),
  isAxiosError: jest.fn(() => false),
}));

const originalConsoleError = console.error;
let consoleErrorSpy;

beforeAll(() => {
  consoleErrorSpy = jest.spyOn(console, 'error').mockImplementation((...args) => {
    const [message = ''] = args;

    if (
      typeof message === 'string' &&
      (
        message.includes('ReactDOMTestUtils.act is deprecated in favor of React.act') ||
        message.includes('A suspended resource finished loading inside a test') ||
        message.includes('inside a test was not wrapped in act(...)')
      )
    ) {
      return;
    }

    originalConsoleError(...args);
  });
});

afterAll(() => {
  consoleErrorSpy?.mockRestore?.();
});
