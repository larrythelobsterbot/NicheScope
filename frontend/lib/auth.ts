export type DashboardAccessDecision = "allow" | "challenge" | "misconfigured";

type Environment = Record<string, string | undefined>;

function constantTimeEqual(left: string, right: string): boolean {
  const maxLength = Math.max(left.length, right.length);
  let difference = left.length ^ right.length;

  for (let index = 0; index < maxLength; index += 1) {
    difference |= (left.charCodeAt(index) || 0) ^ (right.charCodeAt(index) || 0);
  }

  return difference === 0;
}

function decodeBasicCredentials(header: string | null): [string, string] | null {
  if (!header?.startsWith("Basic ")) return null;

  try {
    const decoded = globalThis.atob(header.slice(6));
    const separator = decoded.indexOf(":");
    if (separator < 0) return null;
    return [decoded.slice(0, separator), decoded.slice(separator + 1)];
  } catch {
    return null;
  }
}

export function decideDashboardAccess(
  authorizationHeader: string | null,
  env: Environment = process.env,
): DashboardAccessDecision {
  const expectedUsername = env.NICHESCOPE_AUTH_USERNAME?.trim();
  const expectedPassword = env.NICHESCOPE_AUTH_PASSWORD;
  const configured = Boolean(expectedUsername && expectedPassword);

  if (!configured) {
    return env.NODE_ENV === "production" ? "misconfigured" : "allow";
  }

  const credentials = decodeBasicCredentials(authorizationHeader);
  if (!credentials) return "challenge";

  const [username, password] = credentials;
  return constantTimeEqual(username, expectedUsername!) &&
    constantTimeEqual(password, expectedPassword!)
    ? "allow"
    : "challenge";
}
