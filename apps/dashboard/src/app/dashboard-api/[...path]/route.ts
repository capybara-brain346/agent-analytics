import type { NextRequest } from "next/server";

// Same-origin proxy to the FastAPI back end. The back end has no CORS, and the
// API token must stay on the server. The browser calls
// /dashboard-api/api/overview and this handler forwards it to ${API_URL}/api/overview.
// Both variables are read at request time, never at build time.
type Context = { params: Promise<{ path: string[] }> };

function json(status: number, code: string, message: string) {
  return Response.json(
    { detail: { code, message } },
    { status, headers: { "cache-control": "no-store" } },
  );
}

async function forward(request: NextRequest, { params }: Context) {
  const { path } = await params;
  const allowed =
    (path[0] === "api" && path.length > 1) ||
    (path.length === 1 && path[0] === "health");
  if (!allowed || path.some((p) => p === "." || p === ".." || p.includes("/")))
    return json(404, "not_found", "Only /api/* and /health are proxied.");
  const base = (process.env.API_URL ?? "http://localhost:8000").replace(
    /\/+$/,
    "",
  );
  const token = process.env.API_TOKEN;
  const headers = new Headers();
  headers.set("accept", "application/json");
  if (token) headers.set("authorization", `Bearer ${token}`);
  const init: RequestInit & { duplex?: "half" } = {
    method: request.method,
    headers,
    cache: "no-store",
    redirect: "manual",
  };
  if (request.method === "POST") {
    const type = request.headers.get("content-type");
    if (type) headers.set("content-type", type);
    init.body = request.body;
    init.duplex = "half";
  }
  const url = `${base}/${path.map(encodeURIComponent).join("/")}${request.nextUrl.search}`;
  let upstream: Response;
  try {
    upstream = await fetch(url, init);
  } catch (error) {
    const reason = error instanceof Error ? error.message : "unknown error";
    return json(
      502,
      "api_unreachable",
      `The API at ${base} did not answer: ${reason}`,
    );
  }
  const out = new Headers({ "cache-control": "no-store" });
  const type = upstream.headers.get("content-type");
  if (type) out.set("content-type", type);
  return new Response(upstream.body, { status: upstream.status, headers: out });
}

export const GET = forward;
export const POST = forward;
export const DELETE = forward;
