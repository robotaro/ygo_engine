<script>
  // "My Cards": your library, the booster-pack shop, and the single-card shop.
  // Spend Duelist Points to open packs or buy specific cards; sell duplicates
  // back for a fraction of their value.
  import { profile, refreshProfile } from './store.js'
  import { getJSON, postJSON } from './api.js'
  import { cardImg, debounce } from './util.js'
  import Modal from './Modal.svelte'

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
  let activeGameTitle = $derived(games.find((g) => g.key === activeGame)?.title ?? '')

  // A foil booster-pack wrapper: serrated crimp on the top/bottom edges (one polygon,
  // computed once) and a hue derived from the pack name so a shelf of packs looks varied.
  const SERRATE = (() => {
    const n = 13, d = 2.6, step = 100 / n, pts = [[0, d]]
    for (let i = 0; i < n; i++) { pts.push([(i + 0.5) * step, 0]); pts.push([(i + 1) * step, d]) }
    pts.push([100, 100 - d])
    for (let i = n - 1; i >= 0; i--) { pts.push([(i + 0.5) * step, 100]); pts.push([i * step, 100 - d]) }
    return 'polygon(' + pts.map((p) => p[0].toFixed(2) + '% ' + p[1].toFixed(2) + '%').join(',') + ')'
  })()
  function packHue(name) {
    let h = 0
    for (let i = 0; i < (name || '').length; i++) h = (h * 31 + name.charCodeAt(i)) % 360
    return h
  }

  function flash(text, kind) {
    toast = { text, kind }
    clearTimeout(toastTimer)
    toastTimer = setTimeout(() => (toast = null), 2400)
  }

  async function loadShop() {
    try {
      const d = await getJSON('/api/packs')
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
      library = (await getJSON('/api/collection?' + params)).cards
    } catch {
      library = []
    }
  }

  async function loadSingles() {
    const params = new URLSearchParams({ limit: '120' })
    if (singleQuery) params.set('query', singleQuery)
    try {
      singles = (await getJSON('/api/cards?' + params)).cards
    } catch {
      singles = []
    }
  }

  const loadLibraryDebounced = debounce(loadLibrary, 200)
  const loadSinglesDebounced = debounce(loadSingles, 200)

  // Load the pack shop once; reload library / singles on demand as their search changes.
  $effect(() => {
    loadShop()
  })
  $effect(() => {
    void query
    if (view !== 'library') return
    loadLibraryDebounced()
    return () => loadLibraryDebounced.cancel()
  })
  $effect(() => {
    void singleQuery
    if (view !== 'singles') return
    loadSinglesDebounced()
    return () => loadSinglesDebounced.cancel()
  })

  async function openPack(pack) {
    if (busy) return
    busy = pack.id
    error = ''
    try {
      const d = await postJSON('/api/packs/open', { packId: pack.id })
      reveal = { pack: d.pack, cards: d.pulled }
      packModal = null // make way for the pull reveal
      await refreshProfile() // DP + collection changed
      await loadShop() // affordability may have changed
      if (view === 'library') await loadLibrary()
    } catch (e) {
      error = typeof e.detail === 'string' ? e.detail : 'Could not open this pack.'
    } finally {
      busy = ''
    }
  }

  async function buyCard(card) {
    if (busy) return
    busy = 'buy:' + card.name
    error = ''
    try {
      const d = await postJSON('/api/shop/buy', { name: card.name })
      flash(`Bought ${card.name} · ◈${d.spent.toLocaleString()}`, 'spend')
      await refreshProfile() // DP + collection changed (affordability is derived from dp)
    } catch (e) {
      error = typeof e.detail === 'string' ? e.detail : 'Could not buy this card.'
    } finally {
      busy = ''
    }
  }

  async function sellCard(card) {
    if (busy) return
    busy = 'sell:' + card.name
    error = ''
    try {
      const d = await postJSON('/api/shop/sell', { name: card.name })
      flash(`Sold ${card.name} · +◈${d.earned.toLocaleString()}`, 'earn')
      await refreshProfile()
      await loadLibrary() // owned count dropped (card may now be gone)
    } catch (e) {
      error = typeof e.detail === 'string' ? e.detail : 'Could not sell this card.'
    } finally {
      busy = ''
    }
  }

  // Rarity → a CSS class that escalates brightness (single-accent palette, no new colours).
  function rarClass(rarity) {
    return 'r-' + (rarity || 'Common').toLowerCase().replace(/\s+/g, '-')
  }

  let packModal = $state(null) // a pack's full contents { name, groups, price, ... }
  let cardLocator = $state(null) // where to grind a covered card { name, packs }
  let cardDetail = $state(null) // a card shown enlarged with full details (art/stats/text)

  async function openPackModal(packId) {
    cardLocator = null
    error = ''
    try {
      packModal = await getJSON('/api/pack?id=' + encodeURIComponent(packId))
    } catch {
      error = 'Could not load that pack.'
    }
  }

  function openCardLocator(card) {
    cardLocator = { name: card.name, packs: card.inPacks || [] }
  }
</script>

<div class="cards">
  <div class="topbar">
    <div class="seg">
      <button class:active={view === 'packs'} onclick={() => (view = 'packs')}>📦 Booster Packs</button>
      <button class:active={view === 'singles'} onclick={() => (view = 'singles')}>🔍 Find a Card</button>
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
          <button
            class="wrap"
            onclick={() => openPackModal(p.id)}
            title="See what's in {p.name}"
          >
            <div class="foil" style="--h:{packHue(p.name)}; clip-path:{SERRATE}">
              {#if p.art}
                <!-- full-bleed, blurred+dark copy of the flagship art fills the wrapper -->
                <img class="bleed" src={p.art} alt="" aria-hidden="true" loading="lazy" decoding="async" />
              {/if}
              <div class="sheen"></div>
              <div class="hdr"><span class="kicker">{activeGameTitle}</span></div>
              {#if p.art}
                <div class="art">
                  <!-- window shows ONLY the card's illustration (fixed crop) -->
                  <img
                    src={p.art}
                    alt={p.name}
                    loading="lazy"
                    decoding="async"
                    onerror={(e) => (e.currentTarget.closest('.art').style.display = 'none')}
                  />
                </div>
              {/if}
              <div class="ribbon"><span class="nm" title={p.name}>{p.name}</span></div>
              <div class="ftr"><span class="cpp">{p.cardsPerPack} cards per pack</span></div>
            </div>
          </button>
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
    <input class="search" placeholder="Search any card…" bind:value={singleQuery} />
    <p class="hint">
      Cards from booster packs must be pulled — open the pack(s) they're in. Only cards in
      <b>no</b> pack can be bought directly.
    </p>
    {#if singles.length === 0}
      <div class="empty">No cards match.</div>
    {:else}
      <div class="cardgrid">
        {#each singles as c (c.name)}
          {@const orphan = !c.inPacks || c.inPacks.length === 0}
          <div class="owned shopcard" class:poor={orphan && c.buy > dp} title={c.name}>
            <!-- svelte-ignore a11y_no_static_element_interactions -->
            <div
              class="thumb"
              role="button"
              tabindex="0"
              title="Click for details"
              onclick={() => (cardDetail = c)}
              onkeydown={(e) => e.key === 'Enter' && (cardDetail = c)}
            >
              {#if cardImg(c)}
                <img src={cardImg(c)} alt={c.name} loading="lazy" decoding="async" />
              {:else}
                <div class="noart">{c.name}</div>
              {/if}
              <span class="rar {rarClass(c.rarity)}">{c.rarity}</span>
            </div>
            <div class="cn">{c.name}</div>
            {#if orphan}
              <button
                class="act buy"
                disabled={c.buy > dp || busy === 'buy:' + c.name}
                onclick={() => buyCard(c)}
              >
                {busy === 'buy:' + c.name ? '…' : `Buy ◈${c.buy.toLocaleString()}`}
              </button>
            {:else}
              <button class="act locate" onclick={() => openCardLocator(c)}>
                📦 in {c.inPacks.length} pack{c.inPacks.length === 1 ? '' : 's'}
              </button>
            {/if}
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
            <!-- svelte-ignore a11y_no_static_element_interactions -->
            <div
              class="thumb"
              role="button"
              tabindex="0"
              title="Click for details"
              onclick={() => (cardDetail = c)}
              onkeydown={(e) => e.key === 'Enter' && (cardDetail = c)}
            >
              {#if cardImg(c)}
                <img src={cardImg(c)} alt={c.name} loading="lazy" decoding="async" />
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
  <Modal onclose={() => (reveal = null)}>
    <div class="sheet" role="dialog">
      <h3>{reveal.pack}</h3>
      <div class="pulls">
        {#each reveal.cards as c (c.name)}
          <div class="pull" class:new={c.isNew}>
            <div class="thumb">
              {#if cardImg(c)}
                <img src={cardImg(c)} alt={c.name} decoding="async" />
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
  </Modal>
{/if}

{#if cardDetail}
  {@const c = cardDetail}
  {@const orphan = !c.inPacks || c.inPacks.length === 0}
  <Modal onclose={() => (cardDetail = null)}>
    <div class="sheet detail" role="dialog">
      <div class="dart">
        {#if cardImg(c)}
          <img src={cardImg(c)} alt={c.name} decoding="async" />
        {:else}
          <div class="noart">{c.name}</div>
        {/if}
      </div>
      <div class="dinfo">
        <h3>{c.name}</h3>
        <div class="dmeta">
          <span class="rar inline {rarClass(c.rarity)}">{c.rarity}</span>
          <span class="dtype">{c.cardType}{c.subtype ? ` · ${c.subtype}` : ''}</span>
        </div>
        {#if c.cardType === 'monster'}
          <div class="dstats">
            {#if c.attribute}<span>{c.attribute}</span>{/if}
            {#if c.level != null}<span>Level {c.level}</span>{/if}
            {#if c.race}<span>{c.race}</span>{/if}
            <span class="atkdef">ATK {c.attack ?? '?'} · DEF {c.defense ?? '?'}</span>
          </div>
        {/if}
        {#if c.text}<p class="dtext">{c.text}</p>{/if}
        <div class="dactions">
          {#if c.owned != null}
            <span class="ownedtag">You own ×{c.owned}</span>
            <button
              class="act sell"
              disabled={busy === 'sell:' + c.name}
              onclick={() => sellCard(c)}
            >
              {busy === 'sell:' + c.name ? '…' : `Sell ◈${c.sell.toLocaleString()}`}
            </button>
          {:else if orphan}
            <button
              class="act buy"
              disabled={c.buy > dp || busy === 'buy:' + c.name}
              onclick={() => buyCard(c)}
            >
              {busy === 'buy:' + c.name ? '…' : `Buy ◈${c.buy.toLocaleString()}`}
            </button>
          {:else}
            <button class="act locate" onclick={() => { cardDetail = null; openCardLocator(c) }}>
              📦 in {c.inPacks.length} pack{c.inPacks.length === 1 ? '' : 's'}
            </button>
          {/if}
          <button class="close" onclick={() => (cardDetail = null)}>Close</button>
        </div>
      </div>
    </div>
  </Modal>
{/if}

{#if cardLocator}
  <Modal onclose={() => (cardLocator = null)}>
    <div class="sheet narrow" role="dialog">
      <h3>Get “{cardLocator.name}”</h3>
      <p class="sub">Grind one of these packs until it drops:</p>
      <div class="loclist">
        {#each cardLocator.packs as p (p.id + p.rarity)}
          <button class="locrow" onclick={() => openPackModal(p.id)}>
            <span class="ln">{p.name}</span>
            <span class="rar inline {rarClass(p.rarity)}">{p.rarity}</span>
          </button>
        {/each}
      </div>
      <button class="close" onclick={() => (cardLocator = null)}>Close</button>
    </div>
  </Modal>
{/if}

{#if packModal}
  <Modal onclose={() => (packModal = null)}>
    <div class="sheet wide" role="dialog">
      <h3>{packModal.name}</h3>
      <p class="sub">{packModal.cardsPerPack} cards per pack · {packModal.distinct} in set</p>
      <div class="groups">
        {#each packModal.groups as g (g.rarity)}
          <div class="grp">
            <div class="grhead">
              <span class="rar inline {rarClass(g.rarity)}">{g.rarity}</span>
              <span class="gn">{g.cards.length}</span>
            </div>
            <div class="minigrid">
              {#each g.cards as c (c.name)}
                <div class="mini" title={c.name}>
                  {#if cardImg(c)}
                    <img src={cardImg(c)} alt={c.name} loading="lazy" decoding="async" />
                  {:else}
                    <div class="noart">{c.name}</div>
                  {/if}
                </div>
              {/each}
            </div>
          </div>
        {/each}
      </div>
      <div class="modfoot">
        <button class="close" onclick={() => (packModal = null)}>Close</button>
        <button
          class="btn-primary"
          disabled={!packModal.affordable || busy === packModal.id}
          onclick={() => openPack(packModal)}
        >
          {busy === packModal.id ? 'Opening…' : `Open ◈${packModal.price.toLocaleString()}`}
        </button>
      </div>
    </div>
  </Modal>
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
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  .pack.poor {
    opacity: 0.55;
  }
  /* --- foil booster-pack wrapper --- */
  .wrap {
    position: relative;
    width: 100%;
    aspect-ratio: 62 / 100;
    padding: 0;
    border: 0;
    background: transparent;
    cursor: pointer;
    filter: drop-shadow(0 8px 16px rgba(0, 0, 0, 0.5));
    transition: transform 0.12s ease;
  }
  .wrap:hover {
    transform: translateY(-3px);
  }
  .foil {
    position: absolute;
    inset: 0;
    overflow: hidden;
    display: flex;
    flex-direction: column;
    /* clip-path (serrated crimp) is set inline; hue from the pack name */
    background: linear-gradient(
      135deg,
      hsl(var(--h), 55%, 42%),
      hsl(var(--h), 60%, 22%) 45%,
      hsl(var(--h), 52%, 34%)
    );
  }
  /* full-bleed, blurred+dark copy of the flagship art fills the wrapper */
  .foil .bleed {
    position: absolute;
    inset: -20%;
    width: 140%;
    height: 140%;
    object-fit: cover;
    filter: blur(10px) brightness(0.5) saturate(1.1);
    opacity: 0.5;
    z-index: 0;
  }
  .sheen {
    position: absolute;
    inset: 0;
    z-index: 1;
    pointer-events: none;
    background: linear-gradient(115deg, transparent 30%, rgba(255, 255, 255, 0.2) 45%, transparent 60%);
    mix-blend-mode: screen;
  }
  .hdr,
  .art,
  .ribbon,
  .ftr {
    position: relative;
    z-index: 2;
  }
  .hdr {
    padding: 12px 8px 4px;
    text-align: center;
    flex: none;
  }
  .kicker {
    font-size: 9px;
    font-weight: 800;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    color: rgba(255, 255, 255, 0.9);
    text-shadow: 0 1px 2px rgba(0, 0, 0, 0.7);
  }
  /* window: ONLY the card's illustration (one fixed crop of the art box, for every card) */
  /* the illustration is a square, so the window is square; the crop (calibrated) shows
     exactly the art box — no card frame, name bar, stats or type line. */
  .art {
    flex: none;
    margin: 6px 12px 2px;
    aspect-ratio: 1;
    border-radius: 3px;
    overflow: hidden;
    box-shadow: 0 0 0 1px rgba(0, 0, 0, 0.5), 0 2px 8px rgba(0, 0, 0, 0.45);
  }
  .art img {
    position: absolute;
    width: 125%;
    height: auto;
    left: -12.5%;
    top: -32%;
  }
  .ribbon {
    flex: none;
    margin-top: auto;
    padding: 7px 10px 5px;
    text-align: center;
    background: linear-gradient(180deg, rgba(0, 0, 0, 0.28), rgba(0, 0, 0, 0.52));
    border-top: 2px solid rgba(255, 255, 255, 0.45);
    border-bottom: 2px solid rgba(0, 0, 0, 0.4);
  }
  .nm {
    font-size: 13px;
    font-weight: 900;
    line-height: 1.05;
    color: #fff;
    text-shadow: 0 1px 3px rgba(0, 0, 0, 0.85);
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }
  .ftr {
    flex: none;
    padding: 5px 8px 12px;
    text-align: center;
  }
  .cpp {
    font-size: 9px;
    font-weight: 800;
    letter-spacing: 0.09em;
    text-transform: uppercase;
    color: rgba(255, 255, 255, 0.9);
    text-shadow: 0 1px 2px rgba(0, 0, 0, 0.7);
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
    z-index: 110; /* above <Modal> (z-index 100) so a buy/sell toast stays visible */
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

  /* pack-open reveal (the backdrop is provided by <Modal>) */
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

  /* Thumbnails in the shop/library are clickable to open the detail modal. */
  .owned .thumb {
    cursor: pointer;
    transition: box-shadow 0.12s ease;
  }
  .owned .thumb:hover {
    box-shadow: 0 0 0 2px var(--accent);
  }

  /* Card detail modal: big art + name, type, stats and effect text, with the
     shop/library action so you can decide (and act) from one place. */
  .sheet.detail {
    display: flex;
    gap: 18px;
    text-align: left;
    width: min(580px, 94vw);
    align-items: flex-start;
  }
  .sheet.detail h3 {
    margin: 0 0 8px;
  }
  .dart {
    flex: none;
    width: 210px;
    aspect-ratio: 813 / 1185;
    border-radius: var(--r);
    overflow: hidden;
    background: var(--surface-3);
  }
  .dart img {
    width: 100%;
    height: 100%;
    object-fit: contain;
  }
  .dinfo {
    flex: 1;
    min-width: 0;
  }
  .dmeta {
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
    margin-bottom: 8px;
  }
  .dtype {
    font-size: 12px;
    color: var(--muted);
    text-transform: capitalize;
  }
  .dstats {
    display: flex;
    flex-wrap: wrap;
    gap: 6px 12px;
    font-size: 12px;
    color: var(--muted);
    margin-bottom: 10px;
  }
  .dstats .atkdef {
    color: var(--accent);
    font-weight: 700;
  }
  .dtext {
    font-size: 13px;
    line-height: 1.45;
    color: var(--text);
    background: var(--surface-2);
    border-radius: var(--r);
    padding: 10px 12px;
    margin: 0 0 14px;
    max-height: 40vh;
    overflow-y: auto;
  }
  .dactions {
    display: flex;
    align-items: center;
    gap: 10px;
    flex-wrap: wrap;
  }
  .dactions .close {
    margin-top: 0;
    padding: 8px 18px;
  }
  .ownedtag {
    font-size: 12px;
    font-weight: 700;
    color: var(--muted);
  }

  /* Clickable pack body (opens the contents browser). */
  .hint {
    font-size: 12px;
    color: var(--muted);
    margin: -4px 0 12px;
    max-width: 640px;
  }
  /* "in N packs" locator button on a covered card. */
  .act.locate {
    background: var(--surface-2);
    color: var(--muted);
    border: 1px solid var(--line);
  }
  .act.locate:hover {
    color: var(--accent);
    border-color: var(--accent);
  }
  /* Rarity tag shown inline (in lists / group headers) rather than over art. */
  .rar.inline {
    position: static;
    display: inline-block;
  }

  /* Card-locator + pack-contents modals. */
  .sheet.narrow {
    width: min(420px, 92vw);
    text-align: left;
  }
  .sheet.wide {
    width: min(900px, 94vw);
    max-height: 86vh;
    display: flex;
    flex-direction: column;
    text-align: left;
  }
  .sub {
    margin: -8px 0 14px;
    color: var(--muted);
    font-size: 13px;
  }
  .loclist {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }
  .locrow {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 10px;
    padding: 9px 12px;
    background: var(--surface-2);
    border: 1px solid var(--line);
    border-radius: var(--r);
    cursor: pointer;
  }
  .locrow:hover {
    border-color: var(--accent);
  }
  .locrow .ln {
    font-weight: 700;
    font-size: 13px;
    color: var(--text);
  }
  .groups {
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    gap: 16px;
    padding-right: 4px;
  }
  .grhead {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 6px;
  }
  .grhead .gn {
    color: var(--faint);
    font-size: 11px;
  }
  .minigrid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(64px, 1fr));
    gap: 6px;
  }
  .mini {
    position: relative;
    aspect-ratio: 813 / 1185;
    background: var(--surface-3);
    border-radius: var(--r-sm);
    overflow: hidden;
  }
  .mini img {
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
    object-fit: cover;
  }
  .modfoot {
    display: flex;
    justify-content: flex-end;
    gap: 10px;
    margin-top: 16px;
  }
  .modfoot .close {
    margin-top: 0;
  }
</style>
