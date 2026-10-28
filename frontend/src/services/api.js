import axios from 'axios';

export const resolveApiBaseUrl = () => {
  if (typeof window !== 'undefined') {
    if (window.desktopAPI?.getServerUrl) {
      const desktopUrl = window.desktopAPI.getServerUrl();
      if (desktopUrl) return desktopUrl;
    }
    if (window.__CONFIG__?.API_URL) {
      return window.__CONFIG__.API_URL;
    }
  }
  if (import.meta.env?.VITE_API_URL) {
    return import.meta.env.VITE_API_URL;
  }
  return '/api';
};

const api = axios.create({
  baseURL: resolveApiBaseUrl(),
  timeout: 30000,
});

// Request interceptor to add JWT to headers
api.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// Response interceptor to handle token expiration (401)
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response && error.response.status === 401) {
      localStorage.removeItem('token');
      localStorage.removeItem('role');
      localStorage.removeItem('username');
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);

export default api;
