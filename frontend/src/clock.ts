/* Time source for countdowns. In the replay frame the player sets a virtual
 * time (the server time at the replayed moment); otherwise the wall clock. */
let virtual: number | null = null;

/** Seconds since the epoch. */
export function now(): number {
  return virtual ?? Date.now() / 1000;
}
export function setVirtualNow(t: number | null) {
  virtual = t;
}
export const isVirtual = () => virtual !== null;
