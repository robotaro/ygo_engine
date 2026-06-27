import { writable } from 'svelte/store'

// Live game state pushed from the engine.
export const board = writable(null) // latest board snapshot
export const legal = writable(null) // affordances, present only on your turn
export const awaiting = writable(false) // true == engine is waiting on your move
export const logs = writable([]) // narration lines
export const result = writable(null) // {winner, youWin, reason} when the duel ends
export const connected = writable(false)

let ws = null

export function newGame(seed) {
  if (seed === undefined) seed = Math.floor(Math.random() * 1_000_000)
  if (ws) {
    ws.close()
    ws = null
  }
  logs.set([])
  result.set(null)
  awaiting.set(false)
  board.set(null)
  legal.set(null)

  const proto = location.protocol === 'https:' ? 'wss' : 'ws'
  ws = new WebSocket(`${proto}://${location.host}/ws?seed=${seed}`)
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
        legal.set(msg.legal)
        awaiting.set(true)
        break
      case 'log':
        logs.update((l) => [...l, msg.message].slice(-300))
        break
      case 'result':
        result.set(msg)
        awaiting.set(false)
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
