// Small shared UI helpers used across the launcher, deck tools and the duel view.

// A card's art URL (or null when the card has no image).
export function cardImg(card) {
  return card?.imageId ? `/cards/${card.imageId}.jpg` : null
}

// Turn a deck id / filename into a human label ("dark-magician" -> "dark magician").
export function prettyDeckName(id) {
  return (id ?? '').replace(/[-_]+/g, ' ').trim()
}

// Debounce a function. Returns the wrapped fn plus a `.cancel()` to drop a
// pending call — handy in an $effect teardown. Trailing args are forwarded.
export function debounce(fn, ms = 200) {
  let handle
  const wrapped = (...args) => {
    clearTimeout(handle)
    handle = setTimeout(() => fn(...args), ms)
  }
  wrapped.cancel = () => clearTimeout(handle)
  return wrapped
}
