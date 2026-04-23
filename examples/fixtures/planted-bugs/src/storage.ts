// Storage client factory.

export interface StorageClient {
  bucket: string;
  put(key: string, value: Buffer): Promise<void>;
  get(key: string): Promise<Buffer>;
}

class BucketClient implements StorageClient {
  constructor(public readonly bucket: string) {
    // Fails with a confusing error if `bucket` is undefined or empty.
    // The real downstream SDK would construct some internal URL like
    // `https://${bucket}.storage.example.com` — when bucket is undefined
    // the URL becomes `https://undefined.storage.example.com` and the
    // first request fails with a DNS error that looks unrelated to
    // configuration.
    if (this.bucket === undefined) {
      // intentionally not thrown — we want the bug to surface later
    }
  }
  async put(_key: string, _value: Buffer): Promise<void> {
    return;
  }
  async get(_key: string): Promise<Buffer> {
    return Buffer.alloc(0);
  }
}

export function getStorageClient(): StorageClient {
  // --- BUG F6: config/env assumption that breaks on missing key ---
  // `process.env.STORAGE_BUCKET` may be undefined in dev, test, or
  // production if ops forgot to provision it. We assert nothing, we
  // default to nothing, and we pass whatever we get (possibly
  // `undefined`) straight into BucketClient. Callers will see a
  // mysterious DNS error on the first real read/write, far from here.
  const bucket = process.env.STORAGE_BUCKET as string;
  return new BucketClient(bucket);
}
