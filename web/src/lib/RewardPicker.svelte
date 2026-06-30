<script>
  // Post-victory reward: pick one booster pack from the opponent's game (GBA
  // style) and reveal the cards it gives. Calls `onclaimed` once the player is
  // done so the result overlay can move on.
  import { onMount } from 'svelte'
  import { refreshProfile } from './store.js'

  let { onclaimed } = $props()

  let loading = $state(true)
  let gameTitle = $state('')
  let packs = $state([])
  let busy = $state('') // pack id being opened
  let error = $state('')
  let reveal = $state(null) // { pack, cards } after claiming

  onMount(async () => {
    try {
      const d = await (await fetch('/api/rewards')).json()
      if (!d.pending || !d.packs?.length) {
        onclaimed?.() // nothing to claim — skip straight through
        return
      }
      gameTitle = d.gameTitle
      packs = d.packs
    } catch {
      onclaimed?.()
    } finally {
      loading = false
    }
  })

  async function pick(pack) {
    if (busy) return
    busy = pack.id
    error = ''
    try {
      const res = await fetch('/api/rewards/claim', {
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
      await refreshProfile() // collection changed
    } finally {
      busy = ''
    }
  }

  const img = (c) => (c?.imageId ? `/cards/${c.imageId}.jpg` : null)
</script>

<div class="reward">
  {#if loading}
    <p class="dim">Preparing your reward…</p>
  {:else if reveal}
    <h2>🎉 {reveal.pack}</h2>
    <div class="pulls">
      {#each reveal.cards as c (c.name)}
        <div class="pull" class:new={c.isNew}>
          <div class="thumb">
            {#if img(c)}
              <img src={img(c)} alt={c.name} decoding="async" />
            {:else}
              <div class="noart">{c.name}</div>
            {/if}
            <span class="rar">{c.rarity}</span>
            {#if c.isNew}<span class="badge">NEW</span>{/if}
          </div>
          <div class="cn">{c.name}</div>
        </div>
      {/each}
    </div>
    <button class="btn-primary cont" onclick={() => onclaimed?.()}>Continue ▶</button>
  {:else}
    <h2>🏆 Victory! Choose your reward pack</h2>
    <p class="dim">A booster from {gameTitle} — pick one to open.</p>
    {#if error}<div class="err">{error}</div>{/if}
    <div class="packs">
      {#each packs as p (p.id)}
        <button class="pack" disabled={!!busy} onclick={() => pick(p)} title={p.name}>
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
          <div class="pn">{p.name}</div>
          <div class="pm">{busy === p.id ? 'Opening…' : `${p.cardsPerPack} cards`}</div>
        </button>
      {/each}
    </div>
  {/if}
</div>

<style>
  .reward {
    text-align: center;
    max-width: min(86vw, 760px);
  }
  h2 {
    margin: 0 0 6px;
    color: var(--accent);
  }
  .dim {
    color: var(--muted);
    margin: 0 0 16px;
  }
  .err {
    color: var(--danger);
    background: var(--danger-dim);
    padding: 6px 10px;
    border-radius: var(--r-sm);
    margin-bottom: 10px;
    font-size: 13px;
  }
  .packs {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
    gap: 12px;
    max-height: 56vh;
    overflow-y: auto;
    padding: 2px;
  }
  .pack {
    display: flex;
    flex-direction: column;
    gap: 6px;
    padding: 10px;
    background: var(--surface-2);
    border: 1px solid var(--line);
    border-radius: var(--r-lg);
    cursor: pointer;
    transition: border-color 0.12s, transform 0.12s;
  }
  .pack:hover:not(:disabled) {
    border-color: var(--accent);
    transform: translateY(-2px);
  }
  .pack:disabled {
    opacity: 0.6;
    cursor: default;
  }
  .art {
    width: 100%;
    aspect-ratio: 813 / 1185;
    border-radius: var(--r);
    overflow: hidden;
    background: var(--surface-3);
  }
  .art img {
    width: 100%;
    height: 100%;
    object-fit: contain;
  }
  .pn {
    font-weight: 700;
    font-size: 12px;
    line-height: 1.25;
    min-height: 2.4em;
  }
  .pm {
    font-size: 11px;
    color: var(--muted);
  }
  /* pull reveal */
  .pulls {
    display: flex;
    gap: 12px;
    justify-content: center;
    flex-wrap: wrap;
  }
  .pull {
    width: 120px;
  }
  .thumb {
    position: relative;
    width: 100%;
    aspect-ratio: 813 / 1185;
    background: var(--surface-3);
    border-radius: var(--r);
    overflow: hidden;
  }
  .thumb img {
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
    object-fit: cover;
  }
  .pull.new .thumb {
    box-shadow: 0 0 0 2px var(--accent);
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
  .rar {
    position: absolute;
    top: 4px;
    left: 4px;
    background: rgba(0, 0, 0, 0.6);
    color: var(--accent);
    font-weight: 800;
    font-size: 9px;
    letter-spacing: 0.03em;
    text-transform: uppercase;
    padding: 1px 5px;
    border-radius: var(--r-sm);
  }
  .badge {
    position: absolute;
    top: 4px;
    right: 4px;
    background: var(--accent);
    color: var(--accent-ink);
    font-weight: 800;
    font-size: 10px;
    padding: 1px 6px;
    border-radius: var(--r-sm);
  }
  .cn {
    font-size: 10px;
    font-weight: 700;
    line-height: 1.2;
    margin-top: 3px;
  }
  .cont {
    margin-top: 18px;
    padding: 10px 28px;
  }
</style>
