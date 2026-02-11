import { API_CONFIG } from '@/config/api';

export interface ApiResponse<T = any> {
  data?: T;
  error?: string;
  status: number;
  headers?: Headers;
}

/**
 * Enhanced API request with better CORS and error handling
 */
export async function apiRequest<T = any>(
  endpoint: string,
  options: RequestInit = {}
): Promise<ApiResponse<T>> {
  // Construct the full URL
  const url = `${API_CONFIG.baseURL}${endpoint}`;
  
  // Prepare headers
  const headers = new Headers({
    'Accept': 'application/json',
    ...(options.headers || {})
  });

  // Special handling for FormData
  const isFormData = options.body && options.body instanceof FormData;
  if (!isFormData) {
    headers.set('Content-Type', 'application/json');
  } else {
    // Let the browser set the correct boundary for FormData
    headers.delete('Content-Type');
  }

  // Add cache control headers
  headers.set('Cache-Control', 'no-cache, no-store, must-revalidate');
  headers.set('Pragma', 'no-cache');
  headers.set('Expires', '0');

  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 30000); // 30s timeout

    const response = await fetch(url, {
      ...options,
      headers,
      credentials: 'include',
      signal: controller.signal,
      mode: 'cors',
      cache: 'no-store',
    });

    clearTimeout(timeoutId);

    // Log response headers for debugging
    console.log(`Response from ${endpoint}:`, {
      status: response.status,
      statusText: response.statusText,
      headers: Object.fromEntries(response.headers.entries()),
    });

    // Handle non-2xx responses
    if (!response.ok) {
      let errorData;
      try {
        errorData = await response.json();
      } catch (e) {
        errorData = await response.text().catch(() => ({}));
      }

      return {
        error: errorData?.detail || errorData?.message || response.statusText || 'Request failed',
        status: response.status,
        headers: response.headers,
      };
    }

    // Handle successful responses
    let data;
    const contentType = response.headers.get('content-type');
    
    try {
      data = contentType?.includes('application/json')
        ? await response.json()
        : await response.text();
    } catch (e) {
      console.error('Failed to parse response:', e);
      return {
        error: 'Failed to parse response',
        status: response.status,
        headers: response.headers,
      };
    }

    return { 
      data: data as T, 
      status: response.status,
      headers: response.headers,
    };
  } catch (err) {
    const error = err as Error & { name?: string };
    console.error(`API request to ${url} failed:`, error);
    
    if (error.name === 'AbortError') {
      return {
        error: 'Request timed out',
        status: 408,
      };
    }

    return {
      error: error?.message || 'Network error',
      status: 0, // 0 typically indicates a network error
    };
  }
}

// API Functions
export async function askQuestion(question: string): Promise<ApiResponse<{ answer: string }>> {
  const formData = new FormData();
  formData.append('query', question);
  
  return apiRequest<{ answer: string }>(API_CONFIG.endpoints.ask, {
    method: 'POST',
    body: formData,
  });
}

export async function uploadPdf(file: File): Promise<ApiResponse<{ message: string }>> {
  const formData = new FormData();
  formData.append('file', file);
  
  return apiRequest<{ message: string }>(API_CONFIG.endpoints.upload, {
    method: 'POST',
    body: formData,
  });
}

// Health check to verify backend connection
export async function checkBackendHealth(): Promise<boolean> {
  try {
    const response = await fetch(`${API_CONFIG.baseURL}/health`);
    return response.ok;
  } catch (error) {
    console.error('Backend health check failed:', error);
    return false;
  }
}
