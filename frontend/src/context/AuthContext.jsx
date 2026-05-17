import { createContext, useContext, useEffect, useMemo, useState } from "react";

import api, { tokenStore } from "../api/client";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  async function fetchMe() {
    const { data } = await api.get("/auth/me/");
    setUser(data);
    return data;
  }

  useEffect(() => {
    if (!tokenStore.getAccess()) {
      setLoading(false);
      return;
    }

    fetchMe()
      .catch(() => {
        tokenStore.clear();
        setUser(null);
      })
      .finally(() => setLoading(false));
  }, []);

  async function login(username, password) {
    const { data } = await api.post("/auth/login/", { username, password });
    tokenStore.set(data);
    return fetchMe();
  }

  async function register(payload) {
    const { data } = await api.post("/auth/register/", payload);
    tokenStore.set(data);
    setUser(data.user);
    return data.user;
  }

  async function logout() {
    const refresh = tokenStore.getRefresh();
    try {
      if (refresh) await api.post("/auth/logout/", { refresh });
    } finally {
      tokenStore.clear();
      setUser(null);
    }
  }

  const value = useMemo(
    () => ({
      user,
      loading,
      isAuthenticated: Boolean(user),
      login,
      register,
      logout,
      refreshUser: fetchMe,
    }),
    [user, loading]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside AuthProvider");
  return context;
}
