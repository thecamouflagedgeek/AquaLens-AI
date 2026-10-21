import axios from 'axios';
export const api = axios.create({ baseURL: import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000', withCredentials: true, timeout: 20000 });
export const get = async (path, params, signal) => (await api.get(path, { params, signal })).data;
export const list = (data) => Array.isArray(data) ? data : Array.isArray(data?.items) ? data.items : [];
export const message = (error) => typeof error?.response?.data?.detail === 'string' ? error.response.data.detail : error?.response?.status === 404 ? 'This backend capability is not available yet.' : error?.response?.status === 401 ? 'Your session has expired. Please sign in again.' : error?.response ? `Request failed (${error.response.status}). Please retry.` : 'Cannot connect to the monitoring backend. Check the API connection and retry.';
export const stationPath = (id, resource) => `/stations/${encodeURIComponent(id)}/${resource}`;
