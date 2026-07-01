// Imperative combat animation, kept out of App.svelte. These functions reach
// into the live DOM to play the attack "bump", the red hit-flash, and to place
// floating damage numbers. They locate board elements by the exact class names /
// data-attributes the mat markup renders — `.slot.mon[data-iid=…]`, `.mat.you`,
// `.hudpanel.opp` / `.hudpanel.you` — and toggle the runtime `.fxhit` class, so
// those selectors must stay in lockstep with Mat.svelte.

export const reduceMotion = () =>
  window.matchMedia?.('(prefers-reduced-motion: reduce)').matches

// The attacker charges its target (a monster, or the foe's HUD bar on a direct
// attack) and recoils. Works from either side of the field.
export function bump(attackerIid, targetIid) {
  const aEl = document.querySelector(`.slot.mon[data-iid="${attackerIid}"]`)
  if (!aEl || !aEl.animate) return
  const mine = !!aEl.closest('.mat.you')
  const tEl =
    targetIid != null
      ? document.querySelector(`.slot.mon[data-iid="${targetIid}"]`)
      : document.querySelector(mine ? '.hudpanel.opp' : '.hudpanel.you')
  const a = aEl.getBoundingClientRect()
  let dx = 0
  let dy = mine ? -44 : 44
  if (tEl) {
    const t = tEl.getBoundingClientRect()
    dx = t.left + t.width / 2 - (a.left + a.width / 2)
    dy = t.top + t.height / 2 - (a.top + a.height / 2)
  }
  const k = 0.6 // charge most of the way, then snap back
  aEl.style.zIndex = '20'
  const anim = aEl.animate(
    [
      { transform: 'translate(0, 0)' },
      { transform: `translate(${dx * k}px, ${dy * k}px) scale(1.1)`, offset: 0.4 },
      { transform: 'translate(0, 0)' },
    ],
    { duration: 440, easing: 'cubic-bezier(.34, 1.15, .5, 1)' },
  )
  anim.onfinish = anim.oncancel = () => (aEl.style.zIndex = '')
}

// A red flash + shake on the thing that got hit. The timeout self-clears the
// class, and is a no-op if the element has since left the DOM.
export function flashHit(el) {
  if (!el) return
  el.classList.remove('fxhit')
  void el.offsetWidth // restart the animation if it's already mid-flight
  el.classList.add('fxhit')
  setTimeout(() => el.classList.remove('fxhit'), 360)
}

// Play a resolved combat cue: bump the attacker, then ~40% in flash the target
// and float the damage from whichever HUD bar took it. `floatDamage` is supplied
// by App (it owns the floating-number list). The impact timeout is one-shot and
// guarded against missing elements, so it needs no explicit teardown.
export function playBattleFx(fx, floatDamage) {
  if (reduceMotion()) return
  bump(fx.attacker, fx.target)
  setTimeout(() => {
    if (fx.target != null) flashHit(document.querySelector(`.slot.mon[data-iid="${fx.target}"]`))
    const dmg = fx.damage || {}
    if (dmg.opp > 0) floatDamage(dmg.opp, document.querySelector('.hudpanel.opp'))
    if (dmg.you > 0) floatDamage(dmg.you, document.querySelector('.hudpanel.you'))
  }, 175)
}
