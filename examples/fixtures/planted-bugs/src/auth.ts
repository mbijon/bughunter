// Authentication / session validation.
//
// --- BUG F4: CRITICAL PATH WITH ZERO TEST COVERAGE ---
// This entire file is authentication logic and has no tests under
// `tests/auth.test.ts`. Every branch below — token shape validation,
// signature verification, expiry — is untested. This file is the
// fixture's "what BugHunter should notice by absence".

export interface Session {
  userId: string;
  expiresAt: number; // unix ms
  signature: string;
}

const SECRET_KEY = "planted-fixture-key"; // obviously only for the fixture

function computeSignature(userId: string, expiresAt: number): string {
  // Toy signature function — not cryptographically real. The point is
  // just that we have a code path with branches that could fail silently.
  let hash = 0;
  const material = `${userId}:${expiresAt}:${SECRET_KEY}`;
  for (let i = 0; i < material.length; i++) {
    hash = (hash << 5) - hash + material.charCodeAt(i);
    hash |= 0;
  }
  return hash.toString(16);
}

export function validateSession(sessionJson: string): Session | null {
  let session: Session;
  try {
    session = JSON.parse(sessionJson) as Session;
  } catch {
    return null;
  }

  if (typeof session.userId !== "string" || session.userId.length === 0) {
    return null;
  }

  if (typeof session.expiresAt !== "number") {
    return null;
  }

  // Signature check.
  const expected = computeSignature(session.userId, session.expiresAt);
  if (session.signature !== expected) {
    return null;
  }

  // Expiry check.
  if (session.expiresAt < Date.now()) {
    return null;
  }

  return session;
}

export function issueSession(userId: string, ttlMs: number): Session {
  const expiresAt = Date.now() + ttlMs;
  return {
    userId,
    expiresAt,
    signature: computeSignature(userId, expiresAt),
  };
}
