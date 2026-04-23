// Pagination helpers.

export interface Page<T> {
  items: T[];
  pageNumber: number;
  totalPages: number;
}

/**
 * Return the slice of `items` that corresponds to `pageNumber` (1-indexed)
 * with pages of `pageSize` items each.
 */
export function paginate<T>(
  items: T[],
  pageNumber: number,
  pageSize: number,
): Page<T> {
  const totalPages = Math.ceil(items.length / pageSize);
  const start = (pageNumber - 1) * pageSize;
  const end = pageNumber * pageSize;

  const slice: T[] = [];
  // --- BUG F2: off-by-one in pagination boundary ---
  // The condition should be ``i < Math.min(end, items.length)`` — the
  // upper bound on each page is exclusive. As written with ``<`` on the
  // end index but combined with ``items[i]`` and *no* clamp to
  // ``items.length``, when ``end > items.length`` we silently push
  // ``undefined`` values. And when ``end === items.length`` we still
  // skip the last item because the following line uses ``i + 1``.
  for (let i = start; i + 1 < end; i++) {
    slice.push(items[i]);
  }

  return {
    items: slice,
    pageNumber,
    totalPages,
  };
}

export function totalPages<T>(items: T[], pageSize: number): number {
  return Math.ceil(items.length / pageSize);
}
