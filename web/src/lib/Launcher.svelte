<script>
  import { newGame, profile } from './store.js'
  import MyDecks from './MyDecks.svelte'
  import Collection from './Collection.svelte'
  import BanlistEditor from './BanlistEditor.svelte'
  import OpponentPicker from './OpponentPicker.svelte'

  // Initial tab is deep-linkable via ?tab=decks|cards|banlist (handy for screenshots).
  let tab = $state(new URLSearchParams(location.search).get('tab') || 'play') // play|decks|cards|banlist
  let formats = $state([])
  let format = $state('none') // active Forbidden/Limited list
  let yourDeck = $state('')
  let oppDeck = $state('')
  let seed = $state('')

  // "Your deck" is chosen from the decks you own (Starter + anything you built).
  let myDecks = $derived($profile?.decks ?? [])

  async function loadFormats() {
    const res = await fetch('/api/formats')
    formats = (await res.json()).formats
  }

  $effect(() => {
    loadFormats()
  })

  // Default the deck picker to your active deck (the Starter to begin with).
  $effect(() => {
    if ((!yourDeck || !myDecks.some((d) => d.id === yourDeck)) && myDecks.length) {
      const active = $profile?.activeDeck
      yourDeck = active && myDecks.some((d) => d.id === active) ? active : myDecks[0].id
    }
  })

  function deckById(id) {
    return myDecks.find((d) => d.id === id)
  }

  function startDuel(yourId = yourDeck, oppId = oppDeck) {
    newGame(seed === '' ? undefined : Number(seed), yourId, oppId)
  }

  // From My Decks / the builder: select the deck and jump to Play to pick a foe.
  function pickAndPlay(id) {
    yourDeck = id
    tab = 'play'
  }
</script>

<div class="launcher">
  <div class="tabs">
    <button class:active={tab === 'play'} onclick={() => (tab = 'play')}>⚔ Play</button>
    <button class:active={tab === 'decks'} onclick={() => (tab = 'decks')}>🗂 My Decks</button>
    <button class:active={tab === 'cards'} onclick={() => (tab = 'cards')}>🃏 My Cards</button>
    <button class:active={tab === 'banlist'} onclick={() => (tab = 'banlist')}>⛔ Banned Cards</button>
  </div>

  {#if tab === 'play'}
    <div class="play">
      <h2>Choose your match</h2>
      <p class="sub">
        Duel with one of <span class="full">your decks</span> — win to earn Duelist Points for packs.
      </p>

      <div class="picks">
        <label class="pick">
          <span class="lbl">Format (banned cards)</span>
          <select bind:value={format}>
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
            {#each myDecks as d (d.id)}
              <option value={d.id}>
                {d.legal ? '' : '⚠ '}{d.name.replace(/[-_]+/g, ' ')} · {d.playablePct}%
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
  {:else if tab === 'decks'}
    <MyDecks onPlay={pickAndPlay} />
  {:else if tab === 'cards'}
    <Collection />
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
