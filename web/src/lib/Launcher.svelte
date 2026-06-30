<script>
  import { newGame } from './store.js'
  import DeckBuilder from './DeckBuilder.svelte'

  let tab = $state('play') // 'play' | 'build'
  let decks = $state([])
  let yourDeck = $state('')
  let oppDeck = $state('')
  let seed = $state('')
  let loaded = $state(false)

  async function loadCatalog(selectAfter = null) {
    const res = await fetch('/api/decks')
    const data = await res.json()
    // Best decks first: legal, then most playable, then by name.
    decks = data.decks.sort(
      (a, b) => b.legal - a.legal || b.playablePct - a.playablePct || a.name.localeCompare(b.name),
    )
    const best = decks.find((d) => d.legal && d.playablePct === 100) || decks[0]
    if (selectAfter && decks.some((d) => d.id === selectAfter)) yourDeck = selectAfter
    else if (!yourDeck) yourDeck = best?.id || ''
    if (!oppDeck) oppDeck = best?.id || ''
    loaded = true
  }

  $effect(() => {
    if (!loaded) loadCatalog()
  })

  function deckById(id) {
    return decks.find((d) => d.id === id)
  }

  function startDuel(yourId = yourDeck, oppId = oppDeck) {
    newGame(seed === '' ? undefined : Number(seed), yourId, oppId)
  }

  function randomOpponent() {
    const pool = decks.filter((d) => d.legal && d.id !== yourDeck)
    if (pool.length) oppDeck = pool[Math.floor(Math.random() * pool.length)].id
  }
</script>

<div class="launcher">
  <div class="tabs">
    <button class:active={tab === 'play'} onclick={() => (tab = 'play')}>⚔ Play</button>
    <button class:active={tab === 'build'} onclick={() => (tab = 'build')}>🛠 Build a Deck</button>
  </div>

  {#if tab === 'play'}
    <div class="play">
      <h2>Choose your decks</h2>
      <p class="sub">
        {decks.length} decks available · those marked <span class="full">100%</span> play with every
        effect working today.
      </p>

      <div class="picks">
        <label class="pick">
          <span class="lbl">Your deck</span>
          <select bind:value={yourDeck}>
            {#each decks as d (d.id)}
              <option value={d.id}>
                {d.legal ? '' : '⚠ '}{d.name} · {d.source} · {d.playablePct}%
              </option>
            {/each}
          </select>
        </label>

        <label class="pick">
          <span class="lbl">Opponent <button class="rnd" onclick={randomOpponent}>🎲</button></span>
          <select bind:value={oppDeck}>
            {#each decks as d (d.id)}
              <option value={d.id}>
                {d.legal ? '' : '⚠ '}{d.name} · {d.source} · {d.playablePct}%
              </option>
            {/each}
          </select>
        </label>
      </div>

      {#if deckById(yourDeck)}
        {@const d = deckById(yourDeck)}
        <div class="info">
          You: main {d.main}, extra {d.extra} · {d.legal ? 'legal' : 'not tournament-legal'} · {d.playablePct}%
          playable
        </div>
      {/if}

      <div class="go">
        <input class="seed" placeholder="seed (optional)" bind:value={seed} />
        <button class="start" onclick={() => startDuel()} disabled={!yourDeck || !oppDeck}>
          Start Duel ▶
        </button>
      </div>
    </div>
  {:else}
    <div class="build">
      <DeckBuilder onSaved={(id) => loadCatalog(id)} onPlay={(id) => startDuel(id, oppDeck)} />
    </div>
  {/if}
</div>

<style>
  .launcher {
    grid-column: 1 / -1;
    display: flex;
    flex-direction: column;
    min-height: 0;
    height: calc(100vh - 90px);
  }
  .tabs {
    display: flex;
    gap: 6px;
    margin-bottom: 12px;
  }
  .tabs button {
    background: #222;
    color: #bbb;
    border: 1px solid #333;
  }
  .tabs button.active {
    background: #b8923a;
    color: #1a1a1a;
  }
  .play {
    max-width: 640px;
  }
  h2 {
    color: #d9bf7a;
    margin: 6px 0;
  }
  .sub {
    color: #999;
    font-size: 13px;
    margin: 0 0 18px;
  }
  .full {
    color: #8dff9e;
    font-weight: 700;
  }
  .picks {
    display: flex;
    flex-direction: column;
    gap: 14px;
  }
  .pick {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }
  .lbl {
    font-size: 12px;
    color: #bbb;
    display: flex;
    align-items: center;
    gap: 8px;
  }
  select,
  input {
    background: #222;
    border: 1px solid #444;
    color: #eee;
    border-radius: 5px;
    padding: 8px;
    font-size: 14px;
  }
  .rnd {
    padding: 1px 7px;
    font-size: 12px;
    background: #333;
    color: #eee;
  }
  .info {
    margin-top: 12px;
    font-size: 12px;
    color: #9fd9a9;
  }
  .go {
    margin-top: 22px;
    display: flex;
    gap: 10px;
    align-items: center;
  }
  .seed {
    width: 150px;
  }
  .start {
    background: #2a8a4a;
    color: #fff;
    font-size: 15px;
    padding: 9px 20px;
  }
  .start:hover {
    background: #36a85c;
  }
  button:disabled {
    opacity: 0.4;
    cursor: not-allowed;
  }
  .build {
    flex: 1;
    min-height: 0;
  }
</style>
