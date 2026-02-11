// API configuration
export const API_CONFIG = {
  // In development, use the Next.js API route proxy
  // In production, use DIRECT Railway URL to avoid Vercel timeouts (502)
  baseURL: process.env.NODE_ENV === 'development'
    ? '/api'
    : 'https://documind-ai-production-1d3c.up.railway.app',

  // API endpoints
  endpoints: {
    ask: '/ask',
    upload: '/upload',
  },

  // Default headers for API requests
  headers: {
    'Content-Type': 'application/json',
    'Accept': 'application/json',
  },
};
