// API configuration
export const API_CONFIG = {
  // In development, use the Next.js API route proxy
  // In production, use the actual backend URL
  baseURL: process.env.NODE_ENV === 'development' 
    ? '/api' 
    : process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000',
  
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
