<script>
  // "My Cards": your card library + the booster-pack shop. Buying a pack spends
  // Duelist Points and drops the pulled cards into your library.
  import { profile, refreshProfile } from './store.js'

  let view = $state('shop') // 'shop' | 'library'
  let games = $state([]) // pack shop, grouped by game
  let activeGame = $state('') // which game's packs are shown
  let library = $state([]) // owned cards
  let query = $state('')
  let busy = $state('') // id of the pack currently being opened
  let error = $state('')
  let reveal = $state(null) // { pack, cards } shown after opening a pack

  let dp = $derived($profile?.duelistPoints ?? 0)
  let shownPacks = $derived(games.find((g) => g.key === activeGame)?.packs ?? [])

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

  // Load the shop once; reload the library whenever it's shown or the search changes.
  $effect(() => {
    loadShop()
  })
  $effect(() => {
    const q = query
    if (view !== 'library') return
    const h = setTimeout(loadLibrary, 200)
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

  function img(card) {
    return card?.imageId ? `/cards/${card.imageId}.jpg` : null
  }
</script>

<div class="cards">
  <div class="topbar">
    <div class="seg">
      <button class:active={view === 'shop'} onclick={() => (view = 'shop')}>🛒 Card Shop</button>
      <button class:active={view === 'library'} onclick={() => (view = 'library')}>
        🃏 Your Library{$profile ? ` · ${$profile.collectionDistinct}` : ''}
      </button>
    </div>
    <div class="bal">◈ {dp.toLocaleString()} DP</div>
  </div>

  {#if error}<div class="error">{error}</div>{/if}

  {#if view === 'shop'}
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
            <div class="art"><img src={p.art} alt={p.name} loading="lazy" decoding="async" /></div>
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
            </div>
            <div class="cn">{c.name}</div>
          </div>
        {/each}
      </div>
    {/if}
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
    aspect-ratio: 16 / 10;
    border-radius: var(--r);
    overflow: hidden;
    background: var(--surface-3);
    margin-bottom: 2px;
  }
  .pack .art img {
    width: 100%;
    height: 100%;
    object-fit: cover;
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
