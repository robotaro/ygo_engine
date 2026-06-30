<script>
  // Pick who to duel from the 154 GBA enemy decks, with portraits, grouped by
  // game. Shows the current pick as a card; "Change" opens a searchable grid.
  let { selected = '', format = 'none', onSelect = null } = $props()

  let games = $state([])
  let open = $state(false)
  let query = $state('')
  let gameFilter = $state('') // '' = all games
  let didDefault = false

  // (Re)load the roster whenever the format changes (legality depends on it).
  $effect(() => {
    const fmt = format
    fetch('/api/opponents?format=' + encodeURIComponent(fmt))
      .then((r) => r.json())
      .then((d) => {
        games = d.games
        // First time in: if nothing valid is selected, default to a legal duelist.
        if (!didDefault) {
          didDefault = true
          if (!selected || !flat.some((x) => x.id === selected)) {
            const def = flat.find((x) => x.legal) || flat[0]
            if (def) onSelect?.(def.id)
          }
        }
      })
      .catch(() => {})
  })

  let flat = $derived(
    games.flatMap((g) => g.duelists.map((d) => ({ ...d, game: g.key, gameTitle: g.title }))),
  )
  let current = $derived(flat.find((d) => d.id === selected) || null)

  let shown = $derived(
    games
      .filter((g) => !gameFilter || g.key === gameFilter)
      .map((g) => ({
        ...g,
        duelists: g.duelists.filter(
          (d) => !query || (d.name + ' ' + d.variant).toLowerCase().includes(query.toLowerCase()),
        ),
      }))
      .filter((g) => g.duelists.length),
  )

  function pick(d) {
    onSelect?.(d.id)
    open = false
    query = ''
  }

  function random() {
    const pool = flat.filter((d) => d.legal)
    if (pool.length) onSelect?.(pool[Math.floor(Math.random() * pool.length)].id)
  }

  function initials(name) {
    return (name || '?')
      .split(/\s+/)
      .slice(0, 2)
      .map((w) => w[0])
      .join('')
      .toUpperCase()
  }
</script>

<div class="opp">
  <div class="lbl">
    <span>Opponent</span>
    <button class="rnd" title="Random legal opponent" onclick={random}>🎲</button>
  </div>

  <button class="card" onclick={() => (open = true)}>
    {#if current}
      <div class="face">
        {#if current.portrait}
          <img src={current.portrait} alt="" onerror={(e) => (e.currentTarget.style.display = 'none')} />
        {:else}
          <span class="ini">{initials(current.name)}</span>
        {/if}
      </div>
      <div class="meta">
        <div class="nm">{current.name}</div>
        {#if current.variant}<div class="vr">{current.variant}</div>{/if}
        <div class="sub">
          {current.gameTitle} · {current.main}+{current.extra}
          <span class:bad={!current.legal}>{current.legal ? 'legal' : 'not legal'}</span>
        </div>
      </div>
      <span class="chg">Change ▾</span>
    {:else}
      <div class="meta"><div class="nm">Choose an opponent…</div></div>
      <span class="chg">Browse ▾</span>
    {/if}
  </button>
</div>

{#if open}
  <div
    class="overlay"
    role="button"
    tabindex="0"
    onclick={(e) => e.target === e.currentTarget && (open = false)}
    onkeydown={(e) => e.key === 'Escape' && (open = false)}
  >
    <div class="modal" role="dialog" tabindex="-1">
      <div class="mhead">
        <h3>Choose your opponent</h3>
        <button class="x" onclick={() => (open = false)}>✕</button>
      </div>
      <div class="mbar">
        <input class="search" placeholder="Search duelist…" bind:value={query} />
        <select bind:value={gameFilter}>
          <option value="">All games</option>
          {#each games as g (g.key)}
            <option value={g.key}>{g.title}</option>
          {/each}
        </select>
      </div>

      <div class="mbody">
        {#each shown as g (g.key)}
          <h4>{g.title} <span class="cnt">{g.duelists.length}</span></h4>
          <div class="grid">
            {#each g.duelists as d (d.id)}
              <button
                class="tile"
                class:sel={d.id === selected}
                class:illegal={!d.legal}
                title={d.name + (d.variant ? ' — ' + d.variant : '')}
                onclick={() => pick(d)}
              >
                <div class="tface">
                  {#if d.portrait}
                    <img
                      src={d.portrait}
                      alt=""
                      loading="lazy"
                      decoding="async"
                      onerror={(e) => (e.currentTarget.style.display = 'none')}
                    />
                  {:else}
                    <span class="ini">{initials(d.name)}</span>
                  {/if}
                  {#if !d.legal}<span class="warn" title="Not legal in this format">⚠</span>{/if}
                </div>
                <div class="tn">{d.name}</div>
                {#if d.variant}<div class="tv">{d.variant}</div>{/if}
              </button>
            {/each}
          </div>
        {:else}
          <div class="empty">No duelists match.</div>
        {/each}
      </div>
    </div>
  </div>
{/if}

<style>
  .opp {
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
  .rnd {
    padding: 1px 7px;
    font-size: 12px;
    background: #333;
    color: #eee;
  }
  .card {
    display: flex;
    align-items: center;
    gap: 12px;
    text-align: left;
    background: #1a1a14;
    border: 1px solid #444;
    border-radius: 8px;
    padding: 8px 10px;
    cursor: pointer;
    color: #eee;
  }
  .card:hover {
    border-color: #d9bf7a;
  }
  .face {
    width: 52px;
    height: 52px;
    border-radius: 7px;
    overflow: hidden;
    background: linear-gradient(160deg, #3a3a45, #22222a);
    display: grid;
    place-items: center;
    flex: none;
  }
  .face img {
    width: 100%;
    height: 100%;
    object-fit: cover;
  }
  .ini {
    font-weight: 800;
    color: #d9bf7a;
  }
  .meta {
    flex: 1;
    min-width: 0;
  }
  .nm {
    font-weight: 700;
    font-size: 15px;
  }
  .vr {
    font-size: 11px;
    color: #c9a85a;
  }
  .sub {
    font-size: 11px;
    color: #999;
  }
  .sub .bad {
    color: #ff8a7a;
  }
  .chg {
    font-size: 12px;
    color: #d9bf7a;
    flex: none;
  }

  .overlay {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.6);
    display: grid;
    place-items: center;
    z-index: 50;
  }
  .modal {
    width: min(900px, 92vw);
    height: min(80vh, 720px);
    background: #14140f;
    border: 1px solid #3a3a3a;
    border-radius: 12px;
    display: flex;
    flex-direction: column;
    padding: 14px;
  }
  .mhead {
    display: flex;
    align-items: center;
    justify-content: space-between;
  }
  .mhead h3 {
    margin: 0;
    color: #d9bf7a;
  }
  .x {
    background: #333;
    color: #eee;
  }
  .mbar {
    display: flex;
    gap: 8px;
    margin: 10px 0;
  }
  .search {
    flex: 1;
  }
  input,
  select {
    background: #222;
    border: 1px solid #444;
    color: #eee;
    border-radius: 5px;
    padding: 7px 8px;
  }
  .mbody {
    overflow-y: auto;
    flex: 1;
  }
  h4 {
    color: #c9a85a;
    font-size: 13px;
    margin: 12px 0 6px;
    border-bottom: 1px solid #2c2c2c;
    padding-bottom: 3px;
  }
  .cnt {
    color: #777;
    font-weight: 400;
  }
  .grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(96px, 1fr));
    gap: 8px;
  }
  .tile {
    background: #1d1d24;
    border: 1px solid #333;
    border-radius: 8px;
    padding: 6px;
    cursor: pointer;
    color: #eee;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 4px;
  }
  .tile:hover {
    border-color: #d9bf7a;
  }
  .tile.sel {
    border-color: #6cff9e;
    box-shadow: 0 0 0 1px #6cff9e;
  }
  .tile.illegal {
    opacity: 0.6;
  }
  .tface {
    position: relative;
    width: 100%;
    aspect-ratio: 1;
    border-radius: 6px;
    overflow: hidden;
    background: linear-gradient(160deg, #3a3a45, #22222a);
    display: grid;
    place-items: center;
  }
  .tface img {
    width: 100%;
    height: 100%;
    object-fit: cover;
  }
  .warn {
    position: absolute;
    top: 2px;
    right: 3px;
    color: #ffd76a;
    text-shadow: 0 0 3px #000;
  }
  .tn {
    font-size: 11px;
    font-weight: 600;
    text-align: center;
    line-height: 1.15;
  }
  .tv {
    font-size: 9px;
    color: #c9a85a;
    text-align: center;
    line-height: 1.1;
  }
  .empty {
    color: #888;
    text-align: center;
    padding: 30px;
  }
  button:disabled {
    opacity: 0.4;
    cursor: not-allowed;
  }
</style>
