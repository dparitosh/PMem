/**
 * API Error Handler & Client Utility
 * Comprehensive error handling with timeouts and retries
 */

export class APIError extends Error {
  constructor(message, status = 0, endpoint = '', originalError = null) {
    super(message);
    this.name = 'APIError';
    this.status = status;
    this.endpoint = endpoint;
    this.originalError = originalError;
    this.timestamp = new Date().toISOString();
  }

  isNetworkError() {
    return this.status === 0;
  }

  isTimeout() {
    return this.status === 408;
  }

  isServerError() {
    return this.status >= 500;
  }

  isClientError() {
    return this.status >= 400 && this.status < 500;
  }
}

/**
 * Make API request with timeout, retry, and error handling
 * @param {string} endpoint - API endpoint
 * @param {object} options - Fetch options
 * @param {number} timeoutMs - Timeout in milliseconds (default: 30s)
 * @param {number} maxRetries - Maximum number of retries (default: 2)
 * @returns {Promise<any>} Response JSON
 */
export const apiCall = async (
  endpoint,
  options = {},
  timeoutMs = 30000,
  maxRetries = 2
) => {
  let lastError;

  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    try {
      return await fetchWithTimeout(endpoint, options, timeoutMs);
    } catch (error) {
      lastError = error;

      // Don't retry on client errors (4xx)
      if (error instanceof APIError && error.isClientError()) {
        throw error;
      }

      // Don't retry on last attempt
      if (attempt === maxRetries) {
        throw error;
      }

      // Wait before retrying (exponential backoff: 1s, 2s, 4s)
      const delayMs = Math.pow(2, attempt) * 1000;
      await new Promise(resolve => setTimeout(resolve, delayMs));
    }
  }

  throw lastError;
};

/**
 * Fetch with timeout support
 * @param {string} endpoint - API endpoint
 * @param {object} options - Fetch options
 * @param {number} timeoutMs - Timeout in milliseconds
 * @returns {Promise<any>} Response JSON
 */
export const fetchWithTimeout = async (endpoint, options = {}, timeoutMs = 30000) => {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const response = await fetch(endpoint, {
      ...options,
      signal: controller.signal,
    });

    clearTimeout(timeoutId);

    // Handle HTTP errors
    if (!response.ok) {
      let errorDetail = response.statusText;

      try {
        const errorData = await response.json();
        errorDetail = errorData.detail || errorData.message || errorDetail;
      } catch {
        // Could not parse error response
      }

      throw new APIError(errorDetail, response.status, endpoint);
    }

    // Parse response
    try {
      return await response.json();
    } catch {
      throw new APIError('Invalid JSON response', 0, endpoint);
    }
  } catch (error) {
    clearTimeout(timeoutId);

    if (error instanceof APIError) {
      throw error;
    }

    if (error.name === 'AbortError') {
      throw new APIError(`Request timeout (${timeoutMs}ms)`, 408, endpoint, error);
    }

    if (error instanceof TypeError) {
      throw new APIError('Network connection failed', 0, endpoint, error);
    }

    throw new APIError(error.message || 'Unknown error', 0, endpoint, error);
  }
};

/**
 * Get user-friendly error message
 * @param {APIError|Error} error - Error object
 * @returns {string} User-friendly message
 */
export const getErrorMessage = (error) => {
  if (error instanceof APIError) {
    if (error.isNetworkError()) {
      return 'Network connection failed. Please check your internet connection.';
    }

    if (error.isTimeout()) {
      return 'Request timeout. The server is not responding. Please try again.';
    }

    if (error.isServerError()) {
      return 'Server error. Please try again later or contact support.';
    }

    if (error.status === 401) {
      return 'Unauthorized. Please log in again.';
    }

    if (error.status === 403) {
      return 'Access forbidden. You do not have permission.';
    }

    if (error.status === 404) {
      return 'Resource not found.';
    }

    return error.message || 'An error occurred. Please try again.';
  }

  return error.message || 'An unexpected error occurred.';
};

export default {
  APIError,
  apiCall,
  fetchWithTimeout,
  getErrorMessage,
};
