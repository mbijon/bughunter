// Shared constants. No bugs intentionally planted here.

export const DEFAULT_PAGE_SIZE = 25;
export const MAX_PAGE_SIZE = 200;
export const MIN_PAGE_SIZE = 1;

export const SESSION_TTL_MS = 1000 * 60 * 60 * 24; // 24 hours
export const SHORT_SESSION_TTL_MS = 1000 * 60 * 15; // 15 minutes

export const MAX_RETRY_ATTEMPTS = 3;
export const RETRY_BACKOFF_MS = 500;

export const STORAGE_KEY_PREFIX = "bughunter:";
