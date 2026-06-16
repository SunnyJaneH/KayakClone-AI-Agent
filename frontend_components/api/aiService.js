// src/api/aiService.js
/**
 * AI Service - API calls to AI Recommendation backend
 * Connects to: chat, bundles, watches, price-analysis, quotes
 */

import api from './axios';

const AI_BASE = '/ai';

// ============================================
// Chat API
// ============================================

export const sendChatMessage = async (query, userId, sessionId = null) => {
  const response = await api.post(`${AI_BASE}/chat`, {
    query,
    user_id: userId,
    session_id: sessionId,
    preferences: {}
  });
  return response.data;
};

export const getChatHistory = async (sessionId) => {
  const response = await api.get(`${AI_BASE}/chat/history/${sessionId}`);
  return response.data;
};

export const clearChatSession = async (sessionId) => {
  const response = await api.delete(`${AI_BASE}/chat/session/${sessionId}`);
  return response.data;
};

// ============================================
// Bundles API
// ============================================

export const getBundles = async (params = {}) => {
  const response = await api.get(`${AI_BASE}/bundles`, { params });
  return response.data;
};

export const searchBundles = async (searchParams, sessionId = null) => {
  const response = await api.post(`${AI_BASE}/bundles/search`, {
    ...searchParams,
    session_id: sessionId
  });
  return response.data;
};

export const getBundle = async (bundleId) => {
  const response = await api.get(`${AI_BASE}/bundles/${bundleId}`);
  return response.data;
};

export const getPopularDestinations = async () => {
  const response = await api.get(`${AI_BASE}/bundles/destinations/popular`);
  return response.data;
};

// ============================================
// Watches API
// ============================================

export const createWatch = async (watchData) => {
  const response = await api.post(`${AI_BASE}/watches`, watchData);
  return response.data;
};

export const getWatches = async (userId) => {
  const response = await api.get(`${AI_BASE}/watches`, {
    params: { user_id: userId }
  });
  return response.data;
};

export const deleteWatch = async (watchId) => {
  const response = await api.delete(`${AI_BASE}/watches/${watchId}`);
  return response.data;
};

export const toggleWatch = async (watchId, active) => {
  const response = await api.patch(`${AI_BASE}/watches/${watchId}`, { active });
  return response.data;
};

// ============================================
// Price Analysis API
// ============================================

export const getPriceAnalysis = async (listingType, listingId) => {
  const response = await api.get(
    `${AI_BASE}/price-analysis/analyze/${listingType}/${listingId}`
  );
  return response.data;
};

export const getQuickVerdict = async (listingType, listingId) => {
  const response = await api.get(
    `${AI_BASE}/price-analysis/quick/${listingType}/${listingId}`
  );
  return response.data;
};

export const comparePrices = async (options) => {
  const response = await api.post(`${AI_BASE}/price-analysis/compare`, { options });
  return response.data;
};

export const getBundleAnalysis = async (bundleId) => {
  const response = await api.get(`${AI_BASE}/price-analysis/bundle/${bundleId}`);
  return response.data;
};

// ============================================
// Quotes API
// ============================================

export const generateQuote = async (quoteRequest) => {
  const response = await api.post(`${AI_BASE}/quotes/generate`, quoteRequest);
  return response.data;
};

export const getQuote = async (quoteId) => {
  const response = await api.get(`${AI_BASE}/quotes/${quoteId}`);
  return response.data;
};

export const refreshQuote = async (quoteId) => {
  const response = await api.post(`${AI_BASE}/quotes/${quoteId}/refresh`);
  return response.data;
};

export const initiateBooking = async (quoteId) => {
  const response = await api.post(`${AI_BASE}/quotes/${quoteId}/book`);
  return response.data;
};

export const getListingPolicies = async (listingType, listingId) => {
  const response = await api.get(
    `${AI_BASE}/quotes/policies/${listingType}/${listingId}`
  );
  return response.data;
};

// ============================================
// Health Check
// ============================================

export const checkAiHealth = async () => {
  const response = await api.get(`${AI_BASE}/health`);
  return response.data;
};

export const getAiStatus = async () => {
  const response = await api.get(`${AI_BASE}/status`);
  return response.data;
};

// ============================================
// WebSocket Events
// ============================================

export const createEventsWebSocket = (userId, onMessage, onError) => {
  const wsUrl = `ws://localhost:8000/api/ai/events?user_id=${userId}`;
  const ws = new WebSocket(wsUrl);

  ws.onopen = () => {
    console.log('AI Events WebSocket connected');
  };

  ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      onMessage(data);
    } catch (e) {
      console.error('WebSocket message parse error:', e);
    }
  };

  ws.onerror = (error) => {
    console.error('AI Events WebSocket error:', error);
    if (onError) onError(error);
  };

  ws.onclose = () => {
    console.log('AI Events WebSocket closed');
  };

  return {
    send: (msg) => ws.send(JSON.stringify(msg)),
    ping: () => ws.send(JSON.stringify({ type: 'ping' })),
    clearUnread: () => ws.send(JSON.stringify({ type: 'clear_unread' })),
    getUnread: () => ws.send(JSON.stringify({ type: 'get_unread' })),
    close: () => ws.close()
  };
};

// ============================================
// Default Export
// ============================================

const aiService = {
  sendChatMessage,
  getChatHistory,
  clearChatSession,
  getBundles,
  searchBundles,
  getBundle,
  getPopularDestinations,
  createWatch,
  getWatches,
  deleteWatch,
  toggleWatch,
  getPriceAnalysis,
  getQuickVerdict,
  comparePrices,
  getBundleAnalysis,
  generateQuote,
  getQuote,
  refreshQuote,
  initiateBooking,
  getListingPolicies,
  checkAiHealth,
  getAiStatus,
  createEventsWebSocket
};

export default aiService;
