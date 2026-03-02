import axios from 'axios';

const API_BASE_URL = 'http://localhost:8001';

const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Add response interceptor for error handling
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response) {
      // Server responded with error status
      console.error('API Error:', error.response.data);
      throw new Error(error.response.data.detail || 'An error occurred');
    } else if (error.request) {
      // Request made but no response
      console.error('Network Error:', error.request);
      throw new Error('Network error - please check backend is running');
    } else {
      // Something else happened
      console.error('Error:', error.message);
      throw error;
    }
  }
);

// ==================== USERS ====================

/**
 * Create a new user
 * @param {string} userId - Unique user identifier
 * @returns {Promise<Object>} Created user object
 */
export const createUser = async (userId) => {
  const response = await apiClient.post('/users', { user_id: userId });
  return response.data.data;
};

/**
 * List all users
 * @returns {Promise<Array>} Array of user objects
 */
export const listUsers = async () => {
  const response = await apiClient.get('/users');
  return response.data.data || [];
};

/**
 * Get a specific user by ID
 * @param {string} userId - User identifier
 * @returns {Promise<Object>} User object
 */
export const getUser = async (userId) => {
  const response = await apiClient.get(`/users/${userId}`);
  return response.data.data;
};

// ==================== BLOCKS ====================

/**
 * Create a new memory block
 * @param {string} userId - User identifier
 * @param {string} name - Block name
 * @param {string} description - Block description
 * @returns {Promise<Object>} Created block object
 */
export const createBlock = async (userId, name, description = '') => {
  const response = await apiClient.post('/blocks', {
    user_id: userId,
    name: name,
    description: description || undefined,
  });
  return response.data.data;
};

/**
 * List all blocks for a user
 * @param {string} userId - User identifier
 * @returns {Promise<Array>} Array of block objects
 */
export const listBlocks = async (userId) => {
  const response = await apiClient.get(`/blocks/${userId}`);
  return response.data.data || [];
};

/**
 * Get a specific block by ID
 * @param {string} blockId - Block identifier
 * @returns {Promise<Object>} Block object
 */
export const getBlock = async (userId, blockId) => {
  const response = await apiClient.get(`/blocks/${userId}/${blockId}`);
  return response.data.data;
};

/**
 * Delete a block
 * @param {string} blockId - Block identifier
 * @returns {Promise<Object>} Deletion confirmation
 */
export const deleteBlock = async (userId, blockId) => {
  const response = await apiClient.delete(`/blocks/${userId}/${blockId}`);
  return response.data;
};

// ==================== CHAT ====================

/**
 * Start a new chat session
 * @param {string} userId - User identifier
 * @param {string} blockId - Block identifier
 * @returns {Promise<Object>} Session object with session_id
 */
export const startSession = async (userId, blockId) => {
  const response = await apiClient.post('/chat/sessions', {
    user_id: userId,
    block_id: blockId,
  });
  return response.data.data;
};

/**
 * Send a message in a chat session
 * @param {string} sessionId - Session identifier
 * @param {string} message - User message
 * @returns {Promise<Object>} Response object with assistant reply
 */
export const sendMessage = async (sessionId, message) => {
  const response = await apiClient.post('/chat/message', {
    session_id: sessionId,
    message: message,
  });
  return response.data.data;
};

/**
 * Get chat history for a session
 * @param {string} sessionId - Session identifier
 * @returns {Promise<Array>} Array of message objects
 */
export const getChatHistory = async (sessionId) => {
  const response = await apiClient.get(`/chat/sessions/${sessionId}`);
  return response.data.data;
};

/**
 * Get processing history for a session
 * @param {string} sessionId - Session identifier
 * @returns {Promise<Object>} Processing history with events array
 */
export const getProcessingHistory = async (sessionId) => {
  const response = await apiClient.get(`/chat/sessions/${sessionId}/processing-history`);
  return response.data.data;
};

// ==================== MEMORY ====================

/**
 * Get core memory for a block
 * @param {string} blockId - Block identifier
 * @returns {Promise<Object>} Core memory object
 */
export const getCoreMemory = async (blockId) => {
  const response = await apiClient.get(`/memory/${blockId}/core`);
  return response.data.data;
};

/**
 * Get recursive summary for a block
 * @param {string} blockId - Block identifier
 * @returns {Promise<Object>} Recursive summary object
 */
export const getRecursiveSummary = async (blockId) => {
  const response = await apiClient.get(`/memory/${blockId}/summary`);
  return response.data.data;
};

/**
 * Get semantic memories for a block
 * @param {string} blockId - Block identifier
 * @param {number} limit - Maximum number of memories to retrieve
 * @returns {Promise<Array>} Array of semantic memory objects
 */
export const getSemanticMemories = async (blockId, limit = 20) => {
  const response = await apiClient.get(`/memory/${blockId}/semantic`, {
    params: { limit },
  });
  return response.data.data;
};

/**
 * Search memories
 * @param {string} blockId - Block identifier
 * @param {string} query - Search query
 * @param {number} limit - Maximum number of results
 * @returns {Promise<Array>} Array of matching memory objects
 */
export const searchMemories = async (blockId, query, limit = 10) => {
  const response = await apiClient.post('/memory/search', {
    block_id: blockId,
    query: query,
    limit: limit,
  });
  return response.data.data;
};

export default {
  // Users
  createUser,
  listUsers,
  getUser,

  // Blocks
  createBlock,
  listBlocks,
  getBlock,
  deleteBlock,

  // Chat
  startSession,
  sendMessage,
  getChatHistory,
  getProcessingHistory,

  // Memory
  getCoreMemory,
  getRecursiveSummary,
  getSemanticMemories,
  searchMemories,
};
