import type { Health } from "./types";

// Calls to the back end go through the same-origin proxy at /dashboard-api
// (src/app/dashboard-api/[...path]/route.ts). The API token stays on the server.
const base = "/dashboard-api";

export type ParamValue = string | number | boolean | null | undefined;
export type Params = Record<string, ParamValue | ParamValue[]>;

export class ApiError extends Error {
  status: number;
  code: string;
  constructor(status: number, code: string, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

/** Query string. Empty values are left out. An array repeats the key. */
export function queryString(params: Params = {}) {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    for (const v of Array.isArray(value) ? value : [value]) {
      if (v !== undefined && v !== null && v !== "")
        query.append(key, String(v));
    }
  }
  const text = query.toString();
  return text ? `?${text}` : "";
}

// FastAPI errors: {"detail": {"code","message"}}, {"detail": "text"},
// or a 422 list {"detail": [{"loc": [...], "msg": "..."}]}.
function parseError(status: number, body: unknown): ApiError {
  const detail = (body as { detail?: unknown } | null)?.detail;
  if (Array.isArray(detail)) {
    const text = detail
      .map((d) => {
        const item = d as { loc?: unknown[]; msg?: string };
        const where = (item.loc ?? []).filter((p) => p !== "query").join(".");
        return where ? `${where}: ${item.msg}` : String(item.msg);
      })
      .join("; ");
    return new ApiError(status, "validation_error", text);
  }
  if (detail && typeof detail === "object") {
    const { code, message } = detail as { code?: string; message?: string };
    return new ApiError(
      status,
      code ?? `http_${status}`,
      message ?? `The API answered ${status}.`,
    );
  }
  if (typeof detail === "string")
    return new ApiError(status, `http_${status}`, detail);
  return new ApiError(status, `http_${status}`, `The API answered ${status}.`);
}

const isRaw = (body: unknown): body is Blob | FormData | ArrayBuffer | string =>
  typeof body === "string" ||
  body instanceof Blob ||
  body instanceof FormData ||
  body instanceof ArrayBuffer;

async function request<T>(
  method: "GET" | "POST",
  url: string,
  body: unknown,
  signal: AbortSignal | undefined,
): Promise<T> {
  const init: RequestInit = { method, signal, cache: "no-store" };
  if (body !== undefined) {
    init.body = isRaw(body) ? body : JSON.stringify(body);
    if (!isRaw(body)) init.headers = { "content-type": "application/json" };
  }
  let response: Response;
  try {
    response = await fetch(url, init);
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError")
      throw error;
    throw new ApiError(
      0,
      "network_error",
      "The dashboard server did not answer. Check the connection and retry.",
    );
  }
  const text = await response.text();
  let json: unknown = null;
  try {
    json = text ? JSON.parse(text) : null;
  } catch {
    // A non-JSON body is an error page from a proxy.
  }
  if (!response.ok) throw parseError(response.status, json);
  return json as T;
}

const apiUrl = (path: string, params?: Params) =>
  `${base}/api/${path.replace(/^\/+/, "")}${queryString(params)}`;

/** GET /api/<path>. `path` has no leading "/api", for example "overview". */
export function apiGet<T>(
  path: string,
  params?: Params,
  signal?: AbortSignal,
): Promise<T> {
  return request<T>("GET", apiUrl(path, params), undefined, signal);
}

/** POST /api/<path>. `body` is JSON, or a Blob/FormData for file uploads. */
export function apiPost<T>(
  path: string,
  params?: Params,
  body?: unknown,
  signal?: AbortSignal,
): Promise<T> {
  return request<T>("POST", apiUrl(path, params), body, signal);
}

/** GET /health. The API answers 503 with a normal body when it is unhealthy, so 503 is not an error here. */
export async function apiHealth(signal?: AbortSignal): Promise<Health> {
  try {
    const response = await fetch(`${base}/health`, {
      signal,
      cache: "no-store",
    });
    if (response.ok || response.status === 503)
      return (await response.json()) as Health;
    throw parseError(response.status, await response.json().catch(() => null));
  } catch (error) {
    if (
      error instanceof ApiError ||
      (error instanceof DOMException && error.name === "AbortError")
    )
      throw error;
    throw new ApiError(
      0,
      "network_error",
      "The dashboard server did not answer.",
    );
  }
}
