const normalizeApiBaseUrl = (value: string) => {
  const trimmed = value.trim().replace(/\/+$/, '');
  return trimmed.endsWith('/api') ? trimmed.slice(0, -4) : trimmed;
};

export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL
  ? normalizeApiBaseUrl(import.meta.env.VITE_API_BASE_URL)
  : (import.meta.env.DEV ? 'http://127.0.0.1:30021' : '');
