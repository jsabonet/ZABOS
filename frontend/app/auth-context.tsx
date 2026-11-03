"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";

export type AuthUser = { username: string };
export type AuthStatus = "loading" | "authenticated" | "anonymous" | "error";

type AuthResponse = {
  authenticated: boolean;
  username?: string;
  csrfToken?: string;
};

type AuthContextValue = {
  user: AuthUser | null;
  status: AuthStatus;
  error: string;
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export class ApiRequestError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "ApiRequestError";
  }
}

function readCsrfCookie() {
  const cookie = document.cookie
    .split("; ")
    .find((item) => item.startsWith("csrftoken="));
  return cookie ? decodeURIComponent(cookie.slice("csrftoken=".length)) : null;
}

async function getCsrfToken() {
  const existing = readCsrfCookie();
  if (existing) return existing;

  const response = await fetch("/api/v1/auth/csrf/", {
    credentials: "same-origin",
    cache: "no-store",
  });
  if (!response.ok) {
    throw new Error("Não foi possível iniciar a proteção da sessão.");
  }
  const data = (await response.json()) as AuthResponse;
  if (!data.csrfToken) {
    throw new Error("O servidor não devolveu o token de segurança.");
  }
  return readCsrfCookie() ?? data.csrfToken;
}

export async function apiRequest<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const method = (init.method ?? "GET").toUpperCase();
  const headers = new Headers(init.headers);
  if (typeof init.body === "string" && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  if (!["GET", "HEAD", "OPTIONS", "TRACE"].includes(method)) {
    headers.set("X-CSRFToken", await getCsrfToken());
  }

  const response = await fetch(path, {
    ...init,
    method,
    headers,
    credentials: "same-origin",
    cache: "no-store",
  });
  if (!response.ok) {
    let message = `Não foi possível concluir o pedido (${response.status}).`;
    try {
      const body = (await response.json()) as Record<string, unknown>;
      const detail = body.detail;
      if (typeof detail === "string") message = detail;
      else if (detail) message = JSON.stringify(detail);
    } catch {
      // Preserve the status-based message for non-JSON responses.
    }
    throw new ApiRequestError(message, response.status);
  }
  return (await response.json()) as T;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [status, setStatus] = useState<AuthStatus>("loading");
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    async function restoreSession() {
      try {
        await getCsrfToken();
        const session = await apiRequest<AuthResponse>(
          "/api/v1/auth/session/",
        );
        if (cancelled) return;
        if (session.authenticated && session.username) {
          setUser({ username: session.username });
          setStatus("authenticated");
        } else {
          setUser(null);
          setStatus("anonymous");
        }
      } catch (sessionError) {
        if (cancelled) return;
        setError(
          sessionError instanceof Error
            ? sessionError.message
            : "Não foi possível verificar a sessão.",
        );
        setStatus("error");
      }
    }
    void restoreSession();
    return () => {
      cancelled = true;
    };
  }, []);

  const login = useCallback(async (username: string, password: string) => {
    const response = await apiRequest<AuthResponse>("/api/v1/auth/login/", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    });
    if (!response.authenticated || !response.username) {
      throw new Error("Não foi possível iniciar a sessão.");
    }
    setUser({ username: response.username });
    setError("");
    setStatus("authenticated");
  }, []);

  const logout = useCallback(async () => {
    await apiRequest<AuthResponse>("/api/v1/auth/logout/", {
      method: "POST",
      body: "{}",
    });
    setUser(null);
    setError("");
    setStatus("anonymous");
  }, []);

  return (
    <AuthContext.Provider value={{ user, status, error, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within AuthProvider.");
  }
  return context;
}
