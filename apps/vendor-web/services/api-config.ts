const developmentApiBaseUrl = "http://127.0.0.1:8000/api/v1";

/** Resolve the API base URL without ever sending production users to localhost. */
export function getApiBaseUrl(): string {
  const configured = process.env.NEXT_PUBLIC_API_URL?.trim();
  if (!configured) {
    if (process.env.NODE_ENV === "development") return developmentApiBaseUrl;
    throw new Error("VoltStop API is not configured. Set NEXT_PUBLIC_API_URL for this deployment.");
  }

  let parsed: URL;
  try {
    parsed = new URL(configured);
  } catch {
    throw new Error("NEXT_PUBLIC_API_URL must be an absolute HTTP or HTTPS URL ending in /api/v1.");
  }

  if (
    !["https:", "http:"].includes(parsed.protocol)
    || parsed.pathname.replace(/\/+$/, "") !== "/api/v1"
    || parsed.search
    || parsed.hash
    || parsed.username
    || parsed.password
  ) {
    throw new Error("NEXT_PUBLIC_API_URL must be an absolute HTTP or HTTPS URL ending in /api/v1.");
  }
  if (process.env.NODE_ENV === "production" && parsed.protocol !== "https:") {
    throw new Error("NEXT_PUBLIC_API_URL must use HTTPS in production.");
  }

  return configured.replace(/\/$/, "");
}
