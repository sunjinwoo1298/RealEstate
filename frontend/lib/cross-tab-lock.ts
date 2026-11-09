/**
 * Runs `task` while holding a browser-wide lock, so that only one tab of this
 * origin executes it at a time.
 *
 * Refresh tokens rotate on every use, and the backend treats a second use of
 * an already-rotated token as theft and revokes every session. The refresh
 * cookie is shared by all tabs, so two tabs refreshing at the same moment
 * (opening links in new tabs, reloading several tabs, a browser restoring its
 * session) would both send the same token and log the user out everywhere.
 * Serialising the refresh across tabs means the second tab sends the cookie
 * the first tab's refresh just rotated.
 *
 * Falls back to running the task directly where the Web Locks API is not
 * available (older browsers, non-secure contexts, server rendering).
 */
export function withCrossTabLock<T>(name: string, task: () => Promise<T>): Promise<T> {
  const locks = typeof navigator !== "undefined" ? navigator.locks : undefined;
  if (!locks || typeof locks.request !== "function") {
    return task();
  }
  return locks.request(name, { mode: "exclusive" }, task) as Promise<T>;
}
