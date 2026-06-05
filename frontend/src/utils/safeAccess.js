/**
 * 🔒 MEDIUM PRIORITY: Safe property access utilities
 * Prevents "Cannot read property of undefined/null" errors
 */

/**
 * Safely access nested properties in objects
 * @param {object} obj - The object to access
 * @param {string} path - Dot notation path (e.g., 'user.profile.name')
 * @param {*} defaultValue - Default value if path doesn't exist
 * @returns {*} The property value or defaultValue
 * @example
 *   safeGet(user, 'profile.name', 'Unknown')
 *   safeGet(node, 'properties.labels[0]', 'Unlabeled')
 */
export const safeGet = (obj, path, defaultValue = null) => {
  if (!obj || !path) return defaultValue;
  
  try {
    const value = path.split('.').reduce((val, key) => {
      // Handle array indices like 'properties.items[0]'
      const arrayMatch = key.match(/^(\w+)\[(\d+)\]$/);
      if (arrayMatch) {
        const [, propName, index] = arrayMatch;
        return val?.[propName]?.[parseInt(index)];
      }
      return val?.[key];
    }, obj);
    
    return value !== undefined && value !== null ? value : defaultValue;
  } catch (error) {
    console.warn(`Error accessing path "${path}":`, error);
    return defaultValue;
  }
};

/**
 * Safely access array items with default value
 * @param {array} arr - The array to access
 * @param {number} index - Array index
 * @param {*} defaultValue - Default value if index doesn't exist
 * @returns {*} The array item or defaultValue
 * @example
 *   safeIndex([1, 2, 3], 0, 0)  // 1
 *   safeIndex([1, 2, 3], 10, 0) // 0
 */
export const safeIndex = (arr, index, defaultValue = null) => {
  if (!Array.isArray(arr) || index < 0 || index >= arr.length) {
    return defaultValue;
  }
  return arr[index] !== undefined && arr[index] !== null ? arr[index] : defaultValue;
};

/**
 * Safely call a function with error handling
 * @param {function} fn - Function to call
 * @param {*} defaultValue - Default value on error
 * @param {...args} args - Arguments to pass to function
 * @returns {*} Function result or defaultValue
 * @example
 *   safeCall(() => node.properties.name, 'Unknown')
 *   safeCall(() => data.filter(x => x.id === id), [], id)
 */
export const safeCall = (fn, defaultValue = null, ...args) => {
  try {
    if (typeof fn !== 'function') {
      console.warn('safeCall: fn is not a function', typeof fn);
      return defaultValue;
    }
    const result = fn(...args);
    return result !== undefined ? result : defaultValue;
  } catch (error) {
    console.warn('safeCall error:', error);
    return defaultValue;
  }
};

/**
 * Validate that required properties exist
 * Useful before passing data to components
 * @param {object} obj - Object to validate
 * @param {string[]} requiredKeys - Keys that must exist
 * @returns {boolean} True if all required keys exist and are not null/undefined
 * @example
 *   hasRequired(node, ['id', 'labels', 'properties'])
 */
export const hasRequired = (obj, requiredKeys = []) => {
  if (!obj || typeof obj !== 'object') return false;
  return requiredKeys.every(key => obj[key] !== undefined && obj[key] !== null);
};

/**
 * Filter out null/undefined values from arrays
 * @param {array} arr - Array that may contain null/undefined
 * @returns {array} Filtered array
 * @example
 *   compact([1, null, 2, undefined, 3])  // [1, 2, 3]
 */
export const compact = (arr) => {
  if (!Array.isArray(arr)) return [];
  return arr.filter(item => item !== null && item !== undefined);
};

/**
 * Safely iterate over object properties
 * @param {object} obj - Object to iterate
 * @param {function} callback - Function to call for each property
 * @example
 *   forEachSafe(node.properties, (key, value) => {
 *     console.log(`${key}: ${value}`);
 *   });
 */
export const forEachSafe = (obj, callback) => {
  if (!obj || typeof obj !== 'object' || typeof callback !== 'function') {
    return;
  }
  
  try {
    Object.entries(obj).forEach(([key, value]) => {
      callback(key, value);
    });
  } catch (error) {
    console.warn('forEachSafe error:', error);
  }
};

/**
 * Create a safe copy of an object with defaults
 * Useful for ensuring all expected properties exist
 * @param {object} obj - Source object
 * @param {object} defaults - Default values for missing keys
 * @returns {object} New object with all keys
 * @example
 *   const node = safeDefaults(rawNode, { id: '', labels: [], properties: {} })
 */
export const safeDefaults = (obj, defaults = {}) => {
  const result = { ...defaults };
  
  if (obj && typeof obj === 'object') {
    Object.entries(obj).forEach(([key, value]) => {
      if (value !== null && value !== undefined) {
        result[key] = value;
      }
    });
  }
  
  return result;
};

/**
 * Convert value to string safely
 * Handles null, undefined, objects, arrays
 * @param {*} value - Value to convert
 * @param {string} defaultValue - Default if conversion fails
 * @returns {string} String representation
 * @example
 *   safeString(null, 'N/A')  // 'N/A'
 *   safeString({id: 1}, 'Object')  // 'Object'
 */
export const safeString = (value, defaultValue = 'N/A') => {
  if (value === null || value === undefined) return defaultValue;
  if (typeof value === 'string') return value;
  if (typeof value === 'number' || typeof value === 'boolean') return String(value);
  if (Array.isArray(value)) return `[${value.length} items]`;
  if (typeof value === 'object') return `[Object]`;
  return defaultValue;
};

/**
 * Safely parse JSON
 * @param {string} jsonString - JSON string to parse
 * @param {*} defaultValue - Default if parsing fails
 * @returns {*} Parsed object or defaultValue
 * @example
 *   safeJSON('{"id":1}', {})  // {id: 1}
 *   safeJSON('invalid', {})   // {}
 */
export const safeJSON = (jsonString, defaultValue = null) => {
  try {
    return JSON.parse(jsonString);
  } catch (error) {
    console.warn('safeJSON parse error:', error);
    return defaultValue;
  }
};
