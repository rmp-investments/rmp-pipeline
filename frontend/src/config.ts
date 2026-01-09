// API configuration for different environments
// In development, Vite proxy handles /api routes
// In production, use the full backend URL

export const API_BASE_URL = import.meta.env.VITE_API_URL || '';

export function apiUrl(path: string): string {
  // Ensure path starts with /api
  const normalizedPath = path.startsWith('/') ? path : `/${path}`;
  return `${API_BASE_URL}${normalizedPath}`;
}
