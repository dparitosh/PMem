/**
 * Input Validation Utility
 * Prevents prompt injection and XSS attacks
 */

export class ValidationError extends Error {
  constructor(message) {
    super(message);
    this.name = 'ValidationError';
  }
}

/**
 * Validate chat/query input for LLM
 * @param {string} input - User input to validate
 * @returns {string} Validated and sanitized input
 * @throws {ValidationError} If input is invalid
 */
export const validateChatInput = (input) => {
  // Type check
  if (typeof input !== 'string') {
    throw new ValidationError('Input must be text');
  }

  const trimmed = input.trim();

  // Length validation
  if (trimmed.length < 3) {
    throw new ValidationError('Query too short (minimum 3 characters)');
  }

  if (trimmed.length > 4000) {
    throw new ValidationError('Query too long (maximum 4000 characters)');
  }

  // Detect prompt injection attempts
  const suspiciousPatterns = [
    /ignore\s+(previous\s+)?instructions/i,
    /assume\s+you\s+are/i,
    /without\s+safety|constraints/i,
    /delete\s+(all\s+)?.*\s+(database|records)/i,
    /bypass\s+(authentication|security|restrictions)/i,
    /export\s+.*\s+(password|secret|key|credential)/i,
    /system\s+prompt/i,
    /jailbreak/i,
  ];

  for (const pattern of suspiciousPatterns) {
    if (pattern.test(trimmed)) {
      throw new ValidationError('Query contains suspicious content');
    }
  }

  // Preserve technical syntax (XML, JSON, Cypher, QNames); rendering and
  // transport layers perform their own context-appropriate escaping.
  const sanitized = trimmed
    .replace(/\0/g, '')      // Remove null bytes
    .replace(/\r\n/g, '\n'); // Normalize line endings

  return sanitized;
};

/**
 * Validate search query
 * @param {string} query - Search query
 * @returns {string} Validated query
 */
export const validateSearchQuery = (query) => {
  if (typeof query !== 'string') {
    throw new ValidationError('Query must be text');
  }

  const trimmed = query.trim();

  if (trimmed.length < 1) {
    throw new ValidationError('Query cannot be empty');
  }

  if (trimmed.length > 500) {
    throw new ValidationError('Query too long (maximum 500 characters)');
  }

  // Remove special characters that could break queries
  return trimmed.replace(/[<>{}\\]/g, '');
};

/**
 * Validate file upload
 * @param {File} file - File to validate
 * @param {string[]} allowedExtensions - List of allowed extensions
 * @param {number} maxSize - Max size in MB
 */
export const validateFileUpload = (file, allowedExtensions = [], maxSize = 100) => {
  if (!file) {
    throw new ValidationError('No file selected');
  }

  // Check file extension
  const fileExt = '.' + file.name.split('.').pop().toLowerCase();
  if (allowedExtensions.length > 0 && !allowedExtensions.includes(fileExt)) {
    throw new ValidationError(
      `File type not allowed. Accepted: ${allowedExtensions.join(', ')}`
    );
  }

  // Check file size
  const fileSizeMB = file.size / (1024 * 1024);
  if (fileSizeMB > maxSize) {
    throw new ValidationError(`File too large. Maximum size: ${maxSize}MB`);
  }

  return true;
};

/**
 * Sanitize HTML/text for safe display
 * @param {string} text - Text to sanitize
 * @returns {string} Sanitized text
 */
export const sanitizeText = (text) => {
  if (typeof text !== 'string') return '';

  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#x27;')
    .replace(/\//g, '&#x2F;');
};

const validationUtils = {
  validateChatInput,
  validateSearchQuery,
  validateFileUpload,
  sanitizeText,
  ValidationError,
};

export default validationUtils;
