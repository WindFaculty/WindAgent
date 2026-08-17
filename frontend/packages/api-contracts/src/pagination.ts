/**
 * Cursor Pagination Contract.
 */

export interface PageInfo {
  next_cursor: string | null;
  has_more: boolean;
  total_count?: number | null;
}

export interface CursorPage<T> {
  items: T[];
  page_info: PageInfo;
}
