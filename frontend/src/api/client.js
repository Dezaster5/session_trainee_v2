import axios from "axios";

const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000/api";

export const tokenStore = {
  getAccess: () => localStorage.getItem("accessToken"),
  getRefresh: () => localStorage.getItem("refreshToken"),
  set: ({ access, refresh }) => {
    if (access) localStorage.setItem("accessToken", access);
    if (refresh) localStorage.setItem("refreshToken", refresh);
  },
  clear: () => {
    localStorage.removeItem("accessToken");
    localStorage.removeItem("refreshToken");
  },
};

export const api = axios.create({
  baseURL: API_URL,
  headers: { "Content-Type": "application/json" },
});

api.interceptors.request.use((config) => {
  const token = tokenStore.getAccess();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const original = error.config;
    if (error.response?.status !== 401 || original?._retry) {
      return Promise.reject(error);
    }

    const refresh = tokenStore.getRefresh();
    if (!refresh) {
      tokenStore.clear();
      return Promise.reject(error);
    }

    original._retry = true;
    try {
      const { data } = await axios.post(`${API_URL}/auth/refresh/`, { refresh });
      tokenStore.set({ access: data.access, refresh: data.refresh });
      original.headers = original.headers || {};
      original.headers.Authorization = `Bearer ${data.access}`;
      return api(original);
    } catch (refreshError) {
      tokenStore.clear();
      return Promise.reject(refreshError);
    }
  }
);

export default api;
