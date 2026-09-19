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

export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(path.startsWith('/') ? path : `${API_BASE}/${path}`, {
    headers: { 'Content-Type': 'application/json', ...(init.headers ?? {}) },
    ...init,
  });
  if (!res.ok) {
    const body = await res
      .json()
      .then((b: unknown) => b as ApiError)
      .catch(() => null);
    throw new ApiRequestError(res.status, body);
  }
  return (await res.json()) as T;
}
