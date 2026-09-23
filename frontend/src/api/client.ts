/** Typed API client. All network access goes through here (docs/08-rules.md §5). */

export interface ApiError {
  error: { code: string; message: string; details: unknown };
}

export class ApiRequestError extends Error {
  constructor(
    public readonly status: number,
    public readonly body: ApiError | null,
  ) {
    super(body?.error.message ?? `Request failed with status ${status}`);
  }
}

export const API_BASE = '/api/v1';
const TOKEN_KEY = 'geoguard.token';

/** Access token lives in sessionStorage: cleared when the tab closes (techspec §8). */
export const tokenStore = {
  get: (): string | null => sessionStorage.getItem(TOKEN_KEY),
  set: (t: string): void => sessionStorage.setItem(TOKEN_KEY, t),
  clear: (): void => sessionStorage.removeItem(TOKEN_KEY),
};

const listeners = new Set<() => void>();
/** Fired on 401 so the auth context can drop the session. */
export function onUnauthorized(cb: () => void): () => void {
  listeners.add(cb);
  return () => listeners.delete(cb);
}

export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = tokenStore.get();
  const res = await fetch(path.startsWith('/') ? path : `${API_BASE}/${path}`, {
    ...init,
    headers: {
      // multipart bodies must let the browser set the boundary
      ...(init.body instanceof FormData ? {} : { 'Content-Type': 'application/json' }),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(init.headers ?? {}),
    },
  });
  if (res.status === 204) return undefined as T;
  if (!res.ok) {
    const body = await res
      .json()
      .then((b: unknown) => b as ApiError)
      .catch(() => null);
    if (res.status === 401 && token) {
      tokenStore.clear();
      listeners.forEach((cb) => cb());
    }
    throw new ApiRequestError(res.status, body);
  }
  return (await res.json()) as T;
}
