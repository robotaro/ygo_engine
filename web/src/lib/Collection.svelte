<script>
  // "My Cards": your library, the booster-pack shop, and the single-card shop.
  // Spend Duelist Points to open packs or buy specific cards; sell duplicates
  // back for a fraction of their value.
  import { profile, refreshProfile } from './store.js'

  // Initial view is deep-linkable via the URL hash (#packs|#singles|#library).
  const hashView = location.hash.replace('#', '')
  let view = $state(['packs', 'singles', 'library'].includes(hashView) ? hashView : 'packs')
  let games = $state([]) // pack shop, grouped by game
  let activeGame = $state('') // which game's packs are shown
  let library = $state([]) // owned cards
  let singles = $state([]) // single-card shop search results
  let query = $state('') // library search
  let singleQuery = $state('') // single-card shop search
  let busy = $state('') // id of the action in flight (pack id / buy:name / sell:name)
  let error = $state('')
  let reveal = $state(null) // { pack, cards } shown after opening a pack
  let toast = $state(null) // transient { text, kind } after a buy/sell
  let toastTimer

  let dp = $derived($profile?.duelistPoints ?? 0)
  let shownPacks = $derived(games.find((g) => g.key === activeGame)?.packs ?? [])

  function flash(text, kind) {
    toast = { text, kind }
    clearTimeout(toastTimer)
    toastTimer = setTimeout(() => (toast = null), 2400)
  }

  async function loadShop() {
    try {
      const d = await (await fetch('/api/packs')).json()
      games = d.games
      if (!activeGame && games.length) activeGame = games[0].key
    } catch {
      games = []
    }
  }

  async function loadLibrary() {
    const params = new URLSearchParams()
    if (query) params.set('query', query)
    try {
      library = (await (await fetch('/api/collection?' + params)).json()).cards
    } catch {
      library = []
    }
  }

  async function loadSingles() {
    const params = new URLSearchParams({ limit: '120' })
    if (singleQuery) params.set('query', singleQuery)
    try {
      singles = (await (await fetch('/api/cards?' + params)).json()).cards
    } catch {
      singles = []
    }
  }

  // Load the pack shop once; reload library / singles on demand as their search changes.
  $effect(() => {
    loadShop()
  })
  $effect(() => {
    void query
    if (view !== 'library') return
    const h = setTimeout(loadLibrary, 200)
    return () => clearTimeout(h)
  })
  $effect(() => {
    void singleQuery
    if (view !== 'singles') return
    const h = setTimeout(loadSingles, 200)
    return () => clearTimeout(h)
  })

  async function openPack(pack) {
    if (busy) return
    busy = pack.id
    error = ''
    try {
      const res = await fetch('/api/packs/open', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ packId: pack.id }),
      })
      if (!res.ok) {
        const e = await res.json().catch(() => ({}))
        error = typeof e.detail === 'string' ? e.detail : 'Could not open this pack.'
        return
      }
      const d = await res.json()
      reveal = { pack: d.pack, cards: d.pulled }
      await refreshProfile() // DP + collection changed
      await loadShop() // affordability may have changed
      if (view === 'library') await loadLibrary()
    } finally {
      busy = ''
    }
  }

  async function buyCard(card) {
    if (busy) return
    busy = 'buy:' + card.name
    error = ''
    try {
      const res = await fetch('/api/shop/buy', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: card.name }),
      })
      if (!res.ok) {
        const e = await res.json().catch(() => ({}))
        error = typeof e.detail === 'string' ? e.detail : 'Could not buy this card.'
        return
      }
      const d = await res.json()
      flash(`Bought ${card.name} · ◈${d.spent.toLocaleString()}`, 'spend')
      await refreshProfile() // DP + collection changed (affordability is derived from dp)
    } finally {
      busy = ''
    }
  }

  async function sellCard(card) {
    if (busy) return
    busy = 'sell:' + card.name
    error = ''
    try {
      const res = await fetch('/api/shop/sell', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: card.name }),
      })
      if (!res.ok) {
        const e = await res.json().catch(() => ({}))
        error = typeof e.detail === 'string' ? e.detail : 'Could not sell this card.'
        return
      }
      const d = await res.json()
      flash(`Sold ${card.name} · +◈${d.earned.toLocaleString()}`, 'earn')
      await refreshProfile()
      await loadLibrary() // owned count dropped (card may now be gone)
    } finally {
      busy = ''
    }
  }

  function img(card) {
    return card?.imageId ? `/cards/${card.imageId}.jpg` : null
  }

  // Rarity → a CSS class that escalates brightness (single-accent palette, no new colours).
  function rarClass(rarity) {
    return 'r-' + (rarity || 'Common').toLowerCase().replace(/\s+/g, '-')
  }
</script>

<div class="cards">
  <div class="topbar">
    <div class="seg">
      <button class:active={view === 'packs'} onclick={() => (view = 'packs')}>📦 Booster Packs</button>
      <button class:active={view === 'singles'} onclick={() => (view = 'singles')}>🎴 Single Cards</button>
      <button class:active={view === 'library'} onclick={() => (view = 'library')}>
        🃏 Your Library{$profile ? ` · ${$profile.collectionDistinct}` : ''}
      </button>
    </div>
    <div class="bal">◈ {dp.toLocaleString()} DP</div>
  </div>

  {#if error}<div class="error">{error}</div>{/if}

  {#if view === 'packs'}
    <div class="games">
      {#each games as g (g.key)}
        <button class:active={activeGame === g.key} onclick={() => (activeGame = g.key)}>
          {g.title} <span class="n">{g.packs.length}</span>
        </button>
      {/each}
    </div>
    <div class="packgrid">
      {#each shownPacks as p (p.id)}
        <div class="pack" class:poor={!p.affordable}>
          {#if p.art}
            <div class="art">
              <img
                src={p.art}
                alt={p.name}
                loading="lazy"
                decoding="async"
                onerror={(e) => (e.currentTarget.style.display = 'none')}
              />
            </div>
          {/if}
          <div class="pname" title={p.name}>{p.name}</div>
          <div class="pmeta">{p.cardsPerPack} cards · {p.distinct} in set</div>
          <button
            class="buy"
            disabled={!p.affordable || busy === p.id}
            onclick={() => openPack(p)}
          >
            {busy === p.id ? 'Opening…' : `◈ ${p.price.toLocaleString()}`}
          </button>
        </div>
      {/each}
    </div>
  {:else if view === 'singles'}
    <input class="search" placeholder="Search the card shop…" bind:value={singleQuery} />
    {#if singles.length === 0}
      <div class="empty">No cards match.</div>
    {:else}
      <div class="cardgrid">
        {#each singles as c (c.name)}
          <div class="owned shopcard" class:poor={c.buy > dp} title={c.name}>
            <div class="thumb">
              {#if img(c)}
                <img src={img(c)} alt={c.name} loading="lazy" decoding="async" />
              {:else}
                <div class="noart">{c.name}</div>
              {/if}
              <span class="rar {rarClass(c.rarity)}">{c.rarity}</span>
            </div>
            <div class="cn">{c.name}</div>
            <button
              class="act buy"
              disabled={c.buy > dp || busy === 'buy:' + c.name}
              onclick={() => buyCard(c)}
            >
              {busy === 'buy:' + c.name ? '…' : `◈ ${c.buy.toLocaleString()}`}
            </button>
          </div>
        {/each}
      </div>
    {/if}
  {:else}
    <input class="search" placeholder="Search your library…" bind:value={query} />
    {#if library.length === 0}
      <div class="empty">No cards{query ? ' match.' : ' yet — open a pack!'}</div>
    {:else}
      <div class="cardgrid">
        {#each library as c (c.name)}
          <div class="owned" title={c.name}>
            <div class="thumb">
              {#if img(c)}
                <img src={img(c)} alt={c.name} loading="lazy" decoding="async" />
              {:else}
                <div class="noart">{c.name}</div>
              {/if}
              <span class="qty">×{c.owned}</span>
              <span class="rar {rarClass(c.rarity)}">{c.rarity}</span>
            </div>
            <div class="cn">{c.name}</div>
            <button
              class="act sell"
              disabled={busy === 'sell:' + c.name}
              onclick={() => sellCard(c)}
            >
              {busy === 'sell:' + c.name ? '…' : `Sell ◈${c.sell.toLocaleString()}`}
            </button>
          </div>
        {/each}
      </div>
    {/if}
  {/if}

  {#if toast}
    <div class="toast" class:earn={toast.kind === 'earn'}>{toast.text}</div>
  {/if}
</div>

{#if reveal}
  <div
    class="modal"
    role="button"
    tabindex="0"
    onclick={() => (reveal = null)}
    onkeydown={(e) => e.key === 'Escape' && (reveal = null)}
  >
    <!-- svelte-ignore a11y_no_static_element_interactions -->
    <div class="sheet" role="dialog" onclick={(e) => e.stopPropagation()}>
      <h3>{reveal.pack}</h3>
      <div class="pulls">
        {#each reveal.cards as c (c.name)}
          <div class="pull" class:new={c.isNew}>
            <div class="thumb">
              {#if img(c)}
                <img src={img(c)} alt={c.name} decoding="async" />
              {:else}
                <div class="noart">{c.name}</div>
              {/if}
              {#if c.isNew}<span class="badge">NEW</span>{/if}
            </div>
            <div class="cn">{c.name}</div>
          </div>
        {/each}
      </div>
      <button class="close btn-primary" onclick={() => (reveal = null)}>Add to Library</button>
    </div>
  </div>
{/if}

<style>
  .cards {
    grid-column: 1 / -1;
    display: flex;
    flex-direction: column;
    min-height: 0;
    height: calc(100vh - 90px);
  }
  .topbar {
    display: flex;
    align-items: center;
    gap: 12px;
    margin-bottom: 14px;
  }
  .seg {
    display: flex;
    gap: 6px;
  }
  .seg button,
  .games button {
    background: transparent;
    color: var(--muted);
    border-color: transparent;
  }
  .seg button.active {
    background: var(--surface-2);
    color: var(--accent);
    border-color: var(--line);
  }
  .bal {
    margin-left: auto;
    font-weight: 700;
    color: var(--accent);
    background: var(--surface-2);
    border: 1px solid var(--line);
    padding: 4px 12px;
    border-radius: var(--r-pill);
  }
  .error {
    color: var(--danger);
    background: var(--danger-dim);
    padding: 6px 10px;
    border-radius: var(--r-sm);
    margin-bottom: 10px;
    font-size: 13px;
  }
  .games {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    margin-bottom: 12px;
  }
  .games button.active {
    background: var(--surface-2);
    color: var(--text);
    border-color: var(--accent);
  }
  .games .n {
    color: var(--faint);
    font-size: 11px;
  }
  .packgrid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
    gap: 12px;
    overflow-y: auto;
    align-content: start;
    flex: 1;
    padding-bottom: 12px;
  }
  .pack {
    background: var(--surface);
    border: 1px solid var(--line);
    border-radius: var(--r-lg);
    padding: 12px;
    display: flex;
    flex-direction: column;
    gap: 6px;
  }
  .pack.poor {
    opacity: 0.55;
  }
  .pack .art {
    width: 100%;
    aspect-ratio: 813 / 1185; /* a card's proportions — show it whole, never cropped */
    border-radius: var(--r);
    overflow: hidden;
    background: var(--surface-3);
    margin-bottom: 2px;
  }
  .pack .art img {
    width: 100%;
    height: 100%;
    object-fit: contain;
  }
  .pname {
    font-weight: 700;
    color: var(--text);
    line-height: 1.25;
    min-height: 2.5em;
  }
  .pmeta {
    font-size: 11px;
    color: var(--muted);
  }
  .buy {
    margin-top: auto;
    background: var(--accent);
    color: var(--accent-ink);
    font-weight: 800;
  }
  .buy:disabled {
    background: var(--surface-3);
    color: var(--faint);
  }
  .search {
    margin-bottom: 12px;
    max-width: 320px;
  }
  .empty {
    color: var(--muted);
    padding: 30px;
    text-align: center;
  }
  .cardgrid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(110px, 1fr));
    gap: 10px;
    overflow-y: auto;
    align-content: start;
    flex: 1;
    padding-bottom: 12px;
  }
  .owned .thumb,
  .pull .thumb {
    position: relative;
    width: 100%;
    aspect-ratio: 813 / 1185;
    background: var(--surface-3);
    border-radius: var(--r);
    overflow: hidden;
  }
  .owned img,
  .pull img {
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
    object-fit: cover;
  }
  .noart {
    position: absolute;
    inset: 0;
    display: grid;
    place-items: center;
    padding: 6px;
    text-align: center;
    font-size: 10px;
    color: var(--muted);
  }
  .qty {
    position: absolute;
    bottom: 4px;
    right: 4px;
    background: var(--accent);
    color: var(--accent-ink);
    font-weight: 800;
    font-size: 11px;
    padding: 1px 6px;
    border-radius: var(--r-pill);
  }
  /* Rarity tag — escalates brightness within the single-accent palette. */
  .rar {
    position: absolute;
    top: 4px;
    left: 4px;
    background: rgba(0, 0, 0, 0.6);
    font-weight: 800;
    font-size: 9px;
    letter-spacing: 0.03em;
    text-transform: uppercase;
    padding: 1px 5px;
    border-radius: var(--r-sm);
  }
  .rar.r-common {
    color: var(--faint);
  }
  .rar.r-rare {
    color: var(--muted);
  }
  .rar.r-super-rare {
    color: var(--text);
  }
  .rar.r-ultra-rare {
    color: var(--accent);
  }
  .rar.r-secret-rare {
    color: var(--accent);
    box-shadow: 0 0 0 1px var(--accent) inset;
  }
  /* Buy / sell action buttons on a card tile. */
  .act {
    width: 100%;
    margin-top: 4px;
    padding: 4px 6px;
    font-size: 11px;
    font-weight: 800;
  }
  .shopcard .act.buy {
    background: var(--accent);
    color: var(--accent-ink);
  }
  .act.buy:disabled {
    background: var(--surface-3);
    color: var(--faint);
  }
  .act.sell {
    background: var(--surface-2);
    color: var(--muted);
    border: 1px solid var(--line);
  }
  .act.sell:hover {
    color: var(--text);
    border-color: var(--accent);
  }
  .shopcard.poor {
    opacity: 0.6;
  }
  /* Transient buy/sell confirmation. */
  .toast {
    position: fixed;
    bottom: 22px;
    left: 50%;
    transform: translateX(-50%);
    background: var(--surface);
    border: 1px solid var(--accent);
    color: var(--accent);
    font-weight: 700;
    font-size: 13px;
    padding: 9px 18px;
    border-radius: var(--r-pill);
    z-index: 60;
    box-shadow: 0 6px 24px rgba(0, 0, 0, 0.45);
  }
  .toast.earn {
    border-color: var(--success);
    color: var(--success);
  }
  .cn {
    font-size: 10px;
    font-weight: 700;
    line-height: 1.2;
    margin-top: 3px;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }

  /* pack-open reveal */
  .modal {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.72);
    display: grid;
    place-items: center;
    z-index: 50;
  }
  .sheet {
    background: var(--surface);
    border: 1px solid var(--line-strong);
    border-radius: var(--r-lg);
    padding: 22px;
    max-width: 90vw;
    text-align: center;
  }
  .sheet h3 {
    margin: 0 0 16px;
    color: var(--accent);
  }
  .pulls {
    display: flex;
    gap: 14px;
    justify-content: center;
  }
  .pull {
    width: 140px;
  }
  .pull.new .thumb {
    box-shadow: 0 0 0 2px var(--accent);
  }
  .badge {
    position: absolute;
    top: 5px;
    left: 5px;
    background: var(--accent);
    color: var(--accent-ink);
    font-weight: 800;
    font-size: 10px;
    padding: 1px 6px;
    border-radius: var(--r-sm);
  }
  .close {
    margin-top: 18px;
    padding: 10px 24px;
  }
</style>
