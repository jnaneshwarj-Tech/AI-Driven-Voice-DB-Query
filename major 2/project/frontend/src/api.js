import axios from 'axios';

const BASE = 'http://localhost:8001';

export const api = axios.create({ baseURL: BASE });

// Attach JWT to every request
api.interceptors.request.use(config => {
  const token = sessionStorage.getItem('token');
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

// Auto-logout on 401
api.interceptors.response.use(
  res => res,
  err => {
    if (err.response?.status === 401) {
      sessionStorage.clear();
      window.location.reload();
    }
    return Promise.reject(err);
  }
);

export const registerUser = (name, email, password) =>
  api.post('/auth/register', { name, email, password });

export const loginUser = (email, password) =>
  api.post('/auth/login', { email, password });

export const forgotPassword = (email) =>
  api.post('/auth/forgot-password', { email });

export const resetPassword = (token, new_password, confirm_password) =>
  api.post('/auth/reset-password', { token, new_password, confirm_password });

export const uploadFile = (file, onProgress) => {
  const form = new FormData();
  form.append('file', file);
  return api.post('/upload', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
    onUploadProgress: e => onProgress && onProgress(Math.round((e.loaded * 100) / e.total)),
  });
};

export const runQuery = (query, confirm = false) =>
  api.post('/query', { query, confirm });

export const getStudents = (params) => api.get('/students', { params });

export const getStudent = (usn) => api.get(`/students/${usn}`);

export const getDashboard = () => api.get('/dashboard');

export const getValidation = () => api.get('/validation');

export const getSchema = () => api.get('/schema');

export const clearCache = () => api.delete('/cache');

export const getSemesterData = (usn) => api.get(`/semester/${usn}`);

export const exportCSV = () => {
  const token = sessionStorage.getItem('token');
  window.open(`${BASE}/export/csv?token=${token}`, '_blank');
};

export const exportExcel = () => {
  const token = sessionStorage.getItem('token');
  window.open(`${BASE}/export/excel?token=${token}`, '_blank');
};

export const exportPDF = (query, data, sql) =>
  api.post('/export/pdf', { query, data, sql }, { responseType: 'blob' }).then(res => {
    const url = URL.createObjectURL(new Blob([res.data], { type: 'application/pdf' }));
    const a = document.createElement('a');
    a.href = url;
    a.download = `report_${Date.now()}.pdf`;
    a.click();
    URL.revokeObjectURL(url);
  });
