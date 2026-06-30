<script>
  import { newGame } from './store.js'
  import DeckBuilder from './DeckBuilder.svelte'
  import BanlistEditor from './BanlistEditor.svelte'
  import OpponentPicker from './OpponentPicker.svelte'

  let tab = $state('play') // 'play' | 'build' | 'banlist'
  let decks = $state([])
  let formats = $state([])
  let format = $state('none') // active Forbidden/Limited list
  let yourDeck = $state('')
  let oppDeck = $state('')
  let seed = $state('')
  let loaded = $state(false)

  async function loadFormats() {
    const res = await fetch('/api/formats')
    formats = (await res.json()).formats
  }

  async function loadCatalog(selectAfter = null) {
    const res = await fetch('/api/decks?format=' + encodeURIComponent(format))
    const data = await res.json()
    // Best decks first: legal, then most playable, then by name.
    decks = data.decks.sort(
      (a, b) => b.legal - a.legal || b.playablePct - a.playablePct || a.name.localeCompare(b.name),
    )
    const best = decks.find((d) => d.legal && d.playablePct === 100) || decks[0]
    if (selectAfter && decks.some((d) => d.id === selectAfter)) yourDeck = selectAfter
    else if (!yourDeck) yourDeck = best?.id || ''
    // oppDeck is chosen via the OpponentPicker (defaults itself to a legal duelist).
    loaded = true
  }

  $effect(() => {
    if (!loaded) {
      loadFormats()
      loadCatalog()
    }
  })

  function deckById(id) {
    return decks.find((d) => d.id === id)
  }

  function startDuel(yourId = yourDeck, oppId = oppDeck) {
    newGame(seed === '' ? undefined : Number(seed), yourId, oppId)
  }
</script>

<div class="launcher">
  <div class="tabs">
    <button class:active={tab === 'play'} onclick={() => (tab = 'play')}>⚔ Play</button>
    <button class:active={tab === 'build'} onclick={() => (tab = 'build')}>🛠 Build a Deck</button>
    <button class:active={tab === 'banlist'} onclick={() => (tab = 'banlist')}>⛔ Banned Cards</button>
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
          <span class="lbl">Format (banned cards)</span>
          <select bind:value={format} onchange={() => loadCatalog(yourDeck)}>
            {#each formats as f (f.id)}
              <option value={f.id}>
                {f.name}{f.restricted ? ` · ${f.restricted} restricted` : ''}
              </option>
            {/each}
          </select>
        </label>

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

        <OpponentPicker selected={oppDeck} {format} onSelect={(id) => (oppDeck = id)} />
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
        <button class="start btn-primary" onclick={() => startDuel()} disabled={!yourDeck || !oppDeck}>
          Start Duel ▶
        </button>
      </div>
    </div>
  {:else if tab === 'build'}
    <div class="build">
      <DeckBuilder onSaved={(id) => loadCatalog(id)} onPlay={(id) => startDuel(id, oppDeck)} />
    </div>
  {:else}
    <div class="build">
      <BanlistEditor onSaved={() => loadFormats()} />
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
    justify-content: center;
    gap: 6px;
    margin-bottom: 16px;
  }
  .tabs button {
    background: transparent;
    color: var(--muted);
    border-color: transparent;
  }
  .tabs button:hover {
    background: var(--surface-2);
    color: var(--text);
  }
  .tabs button.active {
    background: var(--surface-2);
    color: var(--accent);
    border-color: var(--line);
  }
  .play {
    max-width: 560px;
    width: 100%;
    margin: 0 auto;
  }
  h2 {
    color: var(--text);
    margin: 6px 0;
  }
  .sub {
    color: var(--muted);
    font-size: 13px;
    margin: 0 0 18px;
  }
  .full {
    color: var(--success);
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
    gap: 5px;
  }
  .lbl {
    font-size: 12px;
    color: var(--muted);
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .info {
    margin-top: 14px;
    font-size: 12px;
    color: var(--success);
  }
  .go {
    margin-top: 24px;
    display: flex;
    gap: 10px;
    align-items: center;
  }
  .seed {
    width: 160px;
  }
  .start {
    font-size: 15px;
    padding: 10px 22px;
  }
  .build {
    flex: 1;
    min-height: 0;
  }
</style>
