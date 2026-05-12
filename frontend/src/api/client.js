import axios from 'axios';

const API_BASE_URL = (import.meta.env.VITE_API_URL || 'http://localhost:8001') + '/api';

export const setAuthToken = (token) => {
  if (token) {
    localStorage.setItem('clerk_token', token);
  } else {
    localStorage.removeItem('clerk_token');
  }
};

export const getAuthToken = () => localStorage.getItem('clerk_token');

const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem('clerk_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  } else {
    console.warn('No auth token found in localStorage');
  }
  return config;
});

apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      setAuthToken(null);
      window.location.href = '/';
    }
    if (error.response) {
      console.error('API Error:', error.response.data);
      throw new Error(error.response.data?.detail || 'An error occurred');
    } else if (error.request) {
      console.error('Network Error:', error.request);
      throw new Error('Network error - please check backend is running');
    } else {
      console.error('Error:', error.message);
      throw error;
    }
  }
);

// ==================== AUTH ====================

export const getCurrentUser = async () => {
  const response = await apiClient.get('/auth/me');
  return response.data;
};

// ==================== BLOCKS ====================

export const createBlock = async (name, description = '', createSemantic = true, createCore = true) => {
  const response = await apiClient.post('/blocks/', {
    name,
    description,
    create_semantic: createSemantic,
    create_core: createCore,
  });
  return response.data;
};

export const listBlocks = async (userId) => {
  const response = await apiClient.get(`/blocks/user/${userId}`);
  return response.data || [];
};

export const getBlock = async (blockId) => {
  const response = await apiClient.get(`/blocks/${blockId}`);
  return response.data;
};

export const deleteBlock = async (blockId) => {
  const response = await apiClient.delete(`/blocks/${blockId}`);
  return response.data;
};

// ==================== CHAT ====================

export const createSession = async (blockId) => {
  const response = await apiClient.post('/chat/sessions', {
    block_id: blockId,
  });
  return response.data;
};

export const getSession = async (sessionId) => {
  const response = await apiClient.get(`/chat/sessions/${sessionId}`);
  return response.data;
};

export const listBlockSessions = async (blockId) => {
  const response = await apiClient.get(`/chat/sessions/block/${blockId}`);
  return response.data || [];
};

export const sendMessage = async (sessionId, message) => {
  const response = await apiClient.post(`/chat/sessions/${sessionId}/message`, {
    message,
  });
  return response.data;
};

export const flushSession = async (sessionId) => {
  const response = await apiClient.post(`/chat/sessions/${sessionId}/flush`);
  return response.data;
};

export const getChatHistory = async (sessionId) => {
  const response = await apiClient.get(`/chat/sessions/${sessionId}/history`);
  return response.data || [];
};

export const getFullSessionContext = async (sessionId) => {
  const response = await apiClient.get(`/chat/sessions/${sessionId}/full-context`);
  return response.data;
};

export const getSessionSummary = async (sessionId) => {
  const response = await apiClient.get(`/chat/sessions/${sessionId}/summary`);
  return response.data;
};

// ==================== MEMORY ====================

export const getCoreMemory = async (blockId) => {
  const response = await apiClient.get(`/memory/core/${blockId}`);
  return response.data;
};

export const updateCoreMemory = async (blockId, personaContent, humanContent) => {
  const response = await apiClient.patch(`/memory/core/${blockId}`, {
    persona_content: personaContent,
    human_content: humanContent,
  });
  return response.data;
};

export const searchMemories = async (blockId, query, topK = 5) => {
  const response = await apiClient.post(`/memory/semantic/${blockId}/search`, {
    query,
    top_k: topK,
  });
  return response.data || [];
};

// ==================== TRANSPARENCY ====================

export const getTransparencyStats = async () => {
  const response = await apiClient.get('/transparency/stats');
  return response.data;
};

export const getProcessingHistory = async (limit = 20) => {
  const response = await apiClient.get(`/transparency/processing-history?limit=${limit}`);
  return response.data || [];
};

// ==================== SESSION PERSISTENCE ====================

const SESSION_STORAGE_KEY = 'memblocks_active_sessions';

export const saveActiveSession = (blockId, sessionId) => {
  try {
    const stored = JSON.parse(localStorage.getItem(SESSION_STORAGE_KEY) || '{}');
    stored[blockId] = sessionId;
    localStorage.setItem(SESSION_STORAGE_KEY, JSON.stringify(stored));
  } catch (e) {
    console.error('Failed to save session to localStorage:', e);
  }
};

export const getActiveSession = (blockId) => {
  try {
    const stored = JSON.parse(localStorage.getItem(SESSION_STORAGE_KEY) || '{}');
    return stored[blockId] || null;
  } catch (e) {
    console.error('Failed to read session from localStorage:', e);
    return null;
  }
};

export const clearActiveSession = (blockId) => {
  try {
    const stored = JSON.parse(localStorage.getItem(SESSION_STORAGE_KEY) || '{}');
    delete stored[blockId];
    localStorage.setItem(SESSION_STORAGE_KEY, JSON.stringify(stored));
  } catch (e) {
    console.error('Failed to clear session from localStorage:', e);
  }
};

// ==================== MEMORY BROWSER ====================

export const getAllBlockMemories = async (blockId, limit = 10, offset = 0) => {
  const response = await apiClient.get(`/memory/all/${blockId}`, {
    params: { semantic_limit: limit, semantic_offset: offset },
  });
  return response.data;
};

export const searchBlockMemory = async (blockId, query = '', searchType = 'all', limit = 10) => {
  const response = await apiClient.post(`/memory/${blockId}/search`, null, {
    params: { query, search_type: searchType, limit },
  });
  return response.data;
};

// ==================== ANALYTICS ====================

export const getTokenUsagePerBlock = async (days = 7) => {
  const response = await apiClient.get(`/analytics/token-usage/per-block`, {
    params: { days },
  });
  return response.data;
};

export const getTokenUsageBlock = async (blockId, days = 7) => {
  const response = await apiClient.get(`/analytics/token-usage/block/${blockId}`, {
    params: { days },
  });
  return response.data;
};

export const getRecentLlmCalls = async (blockId = null, limit = 20) => {
  const response = await apiClient.get(`/analytics/token-usage/recent`, {
    params: { block_id: blockId, limit },
  });
  return response.data;
};

export default {
  setAuthToken,
  getAuthToken,
  getCurrentUser,
  createBlock,
  listBlocks,
  getBlock,
  deleteBlock,
  createSession,
  getSession,
  listBlockSessions,
  sendMessage,
  flushSession,
  getChatHistory,
  getFullSessionContext,
  getSessionSummary,
  getCoreMemory,
  updateCoreMemory,
  searchMemories,
  getTransparencyStats,
  getProcessingHistory,
  saveActiveSession,
  getActiveSession,
  clearActiveSession,
  getAllBlockMemories,
  searchBlockMemory,
  getTokenUsagePerBlock,
  getTokenUsageBlock,
  getRecentLlmCalls,
};
