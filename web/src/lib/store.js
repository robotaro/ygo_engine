import { writable } from 'svelte/store'

// Live game state pushed from the engine.
export const board = writable(null) // latest board snapshot
export const legal = writable(null) // affordances, present only on your main-phase turn
export const responsePrompt = writable(null) // {options, event} during a chain response window
export const targetRequest = writable(null) // {source, prompt, candidates, count} when an effect needs a target
export const choosePrompt = writable(null) // {prompt, options[]} when picking one card (e.g. a Fusion)
export const ritualPrompt = writable(null) // {prompt, required, freeZones, options[]} for Ritual Tributes
export const awaiting = writable(false) // true == engine is waiting on your move
export const logs = writable([]) // narration lines
export const result = writable(null) // {winner, youWin, reason} when the duel ends
export const connected = writable(false) // WebSocket open (i.e. a duel is live)
export const online = writable(false) // backend HTTP reachable (polled)
export const profile = writable(null) // {duelistPoints, collection..., decks, stats}

// Pull the player's save (DP balance, collection size, decks) and broadcast it.
// Call after anything that mutates the profile: pack opens, deck saves, duel end.
export async function refreshProfile() {
  try {
    const r = await fetch('/api/profile')
    if (r.ok) profile.set(await r.json())
  } catch {
    /* offline — leave the last known profile in place */
  }
}

let ws = null
let tournamentMatch = false // was the live duel a tournament round?

// Start a duel that counts as a tournament round (its result advances the bracket).
export function startTournamentDuel(seed, deck, opp) {
  tournamentMatch = true
  newGame(seed, deck, opp)
}

async function advanceTournament(won) {
  try {
    await fetch('/api/tournament/advance', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ won }),
    })
  } catch {
    /* offline — the bracket will reconcile on next load */
  }
  refreshProfile()
}

// Poll the backend so the header can show real server reachability, not just
// whether a duel WebSocket happens to be open.
let healthTimer = null
export function startHealthMonitor() {
  const ping = async () => {
    try {
      const r = await fetch('/api/health')
      online.set(r.ok)
    } catch {
      online.set(false)
    }
  }
  ping()
  refreshProfile()
  if (!healthTimer) healthTimer = setInterval(ping, 5000)
}

// Reset all live-game stores (used on a new game and when leaving to the menu).
function resetGameStores() {
  logs.set([])
  result.set(null)
  awaiting.set(false)
  board.set(null)
  legal.set(null)
  responsePrompt.set(null)
  targetRequest.set(null)
  choosePrompt.set(null)
  ritualPrompt.set(null)
}

// Close any duel and return to the launcher (board === null shows the menu).
export function leaveGame() {
  if (ws) {
    ws.close()
    ws = null
  }
  resetGameStores()
  connected.set(false)
}

export function newGame(seed, deck, opp) {
  if (seed === undefined || seed === '' || seed == null) {
    seed = Math.floor(Math.random() * 1_000_000)
  }
  if (ws) {
    ws.close()
    ws = null
  }
  resetGameStores()

  const proto = location.protocol === 'https:' ? 'wss' : 'ws'
  let q = `seed=${seed}`
  if (deck) q += `&deck=${encodeURIComponent(deck)}`
  if (opp) q += `&opp=${encodeURIComponent(opp)}`
  ws = new WebSocket(`${proto}://${location.host}/ws?${q}`)
  ws.onopen = () => connected.set(true)
  ws.onclose = () => connected.set(false)
  ws.onmessage = (event) => {
    const msg = JSON.parse(event.data)
    switch (msg.type) {
      case 'state':
        board.set(msg.state)
        awaiting.set(false)
        break
      case 'decision':
        board.set(msg.state)
        legal.set(null)
        responsePrompt.set(null)
        targetRequest.set(null)
        choosePrompt.set(null)
        ritualPrompt.set(null)
        if (msg.context === 'response') {
          responsePrompt.set({ options: msg.options, event: msg.event })
        } else if (msg.context === 'target') {
          targetRequest.set({
            source: msg.source,
            prompt: msg.prompt,
            candidates: msg.candidates,
            count: msg.count,
          })
        } else if (msg.context === 'choose') {
          choosePrompt.set({ prompt: msg.prompt, options: msg.options })
        } else if (msg.context === 'tribute') {
          ritualPrompt.set({
            prompt: msg.prompt,
            required: msg.required,
            freeZones: msg.freeZones,
            options: msg.options,
          })
        } else {
          legal.set(msg.legal)
        }
        awaiting.set(true)
        break
      case 'log':
        logs.update((l) => [...l, msg.message].slice(-300))
        break
      case 'result':
        result.set(msg) // includes dpEarned + duelistPoints from the server
        awaiting.set(false)
        if (tournamentMatch) {
          tournamentMatch = false
          advanceTournament(!!msg.youWin) // advance the bracket (also refreshes profile)
        } else {
          refreshProfile() // DP was just awarded — update the header balance
        }
        break
      default:
        break
    }
  }
}

export function sendIntent(intent) {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify(intent))
    awaiting.set(false) // optimistic: stop accepting input until the next prompt
  }
}
