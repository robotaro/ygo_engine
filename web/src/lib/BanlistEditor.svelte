<script>
  // Build your own Forbidden/Limited list. Search the pool, set each card's
  // status (Forbidden / Limited / Semi / Unlimited), name it, and save — it then
  // shows up as a selectable Format in the Play tab and Deck Builder.
  import { getJSON, postJSON } from './api.js'
  import { cardImg, debounce } from './util.js'
  let { onSaved = null } = $props()

  let name = $state('My Banlist')
  let query = $state('')
  let typeFilter = $state('')
  let results = $state([])
  let loading = $state(false)

  let limits = $state({}) // card name -> cap (0 | 1 | 2)
  let formats = $state([]) // existing lists you can start from
  let baseId = $state('')
  let saving = $state(false)
  let savedId = $state(null)

  const STATUSES = [
    { cap: 0, label: 'Forbidden', short: 'F' },
    { cap: 1, label: 'Limited', short: '1' },
    { cap: 2, label: 'Semi', short: '2' },
    { cap: 3, label: 'Unlimited', short: '3' },
  ]

  let restricted = $derived(
    Object.entries(limits)
      .map(([n, cap]) => ({ name: n, cap }))
      .sort((a, b) => a.cap - b.cap || a.name.localeCompare(b.name)),
  )
  let counts = $derived({
    forbidden: restricted.filter((r) => r.cap === 0).length,
    limited: restricted.filter((r) => r.cap === 1).length,
    semi: restricted.filter((r) => r.cap === 2).length,
  })

  // Load existing lists once (to populate the "start from" selector).
  $effect(() => {
    getJSON('/api/formats')
      .then((d) => (formats = d.formats.filter((f) => f.id !== 'none')))
      .catch(() => {})
  })

  // Pool search (debounced).
  async function searchCards() {
    const params = new URLSearchParams({ limit: '150' })
    if (query) params.set('query', query)
    if (typeFilter) params.set('type', typeFilter)
    try {
      results = (await getJSON(`/api/cards?${params}`)).cards
    } catch {
      results = []
    } finally {
      loading = false
    }
  }
  const searchCardsDebounced = debounce(searchCards, 200)
  $effect(() => {
    void query
    void typeFilter
    loading = true
    searchCardsDebounced()
    return () => searchCardsDebounced.cancel()
  })

  function setStatus(cardName, cap) {
    if (cap === 3) {
      const next = { ...limits }
      delete next[cardName]
      limits = next
    } else {
      limits = { ...limits, [cardName]: cap }
    }
  }

  function statusLabel(cap) {
    return STATUSES.find((s) => s.cap === cap)?.label ?? ''
  }

  async function startFrom(id) {
    if (!id) return
    try {
      const data = await getJSON('/api/banlist?id=' + encodeURIComponent(id))
      limits = { ...data.limits }
      if (name === 'My Banlist' && data.name) name = data.name + ' (copy)'
    } catch {
      /* ignore */
    }
  }

  async function save() {
    saving = true
    savedId = null
    try {
      const data = await postJSON('/api/banlists', { name, limits: { ...limits } })
      savedId = data.id
      onSaved?.(data.id)
    } catch {
      /* save failed — leave savedId null so no confirmation shows */
    } finally {
      saving = false
    }
  }
</script>

<div class="editor">
  <!-- Pool: set each card's status -->
  <section class="pool">
    <div class="bar">
      <input class="search" placeholder="Search name or text…" bind:value={query} />
      <select bind:value={typeFilter}>
        <option value="">All types</option>
        <option value="monster">Monsters</option>
        <option value="spell">Spells</option>
        <option value="trap">Traps</option>
      </select>
    </div>
    <div class="list">
      {#if loading}
        <div class="hint">Searching…</div>
      {:else if results.length === 0}
        <div class="hint">No cards match.</div>
      {:else}
        {#each results as card (card.name)}
          {@const cur = limits[card.name] ?? 3}
          <div class="crow" class:restricted={cur < 3}>
            {#if cardImg(card)}
              <img src={cardImg(card)} alt="" loading="lazy" decoding="async" />
            {:else}
              <div class="noimg"></div>
            {/if}
            <span class="cname" title={card.name}>{card.name}</span>
            <div class="seg">
              {#each STATUSES as s (s.cap)}
                <button
                  class="sbtn s{s.cap}"
                  class:on={cur === s.cap}
                  title={s.label}
                  onclick={() => setStatus(card.name, s.cap)}>{s.short}</button
                >
              {/each}
            </div>
          </div>
        {/each}
      {/if}
    </div>
  </section>

  <!-- Current banlist -->
  <section class="panel">
    <input class="bname" bind:value={name} />

    <label class="from">
      <span>Start from</span>
      <select
        bind:value={baseId}
        onchange={() => startFrom(baseId)}
      >
        <option value="">— blank —</option>
        {#each formats as f (f.id)}
          <option value={f.id}>{f.name}</option>
        {/each}
      </select>
    </label>

    <div class="tally">
      <span class="t f">{counts.forbidden} Forbidden</span>
      <span class="t l">{counts.limited} Limited</span>
      <span class="t s">{counts.semi} Semi</span>
    </div>

    <div class="entries">
      {#if restricted.length === 0}
        <div class="hint">No restrictions yet. Set a card to Forbidden, Limited, or Semi.</div>
      {:else}
        {#each restricted as r (r.name)}
          <div class="erow">
            <span class="badge b{r.cap}">{statusLabel(r.cap)}</span>
            <span class="en" title={r.name}>{r.name}</span>
            <button class="rm" title="Remove (unlimited)" onclick={() => setStatus(r.name, 3)}
              >×</button
            >
          </div>
        {/each}
      {/if}
    </div>

    <div class="actions">
      <button class="savebtn btn-primary" onclick={save} disabled={saving || restricted.length === 0}>
        {saving ? 'Saving…' : 'Save Banlist'}
      </button>
      <button class="btn-ghost" onclick={() => (limits = {})} disabled={restricted.length === 0}
        >Clear</button
      >
    </div>
    {#if savedId}<div class="saved">Saved as <code>{savedId}</code> — now selectable as a Format.</div>{/if}
  </section>
</div>

<style>
  .editor {
    display: grid;
    grid-template-columns: 1fr minmax(300px, 360px);
    gap: 14px;
    height: 100%;
    min-height: 0;
  }
  .pool,
  .panel {
    background: var(--surface);
    border: 1px solid var(--line);
    border-radius: var(--r-lg);
    padding: 12px;
    display: flex;
    flex-direction: column;
    min-height: 0;
  }
  .bar {
    display: flex;
    gap: 8px;
    margin-bottom: 10px;
  }
  .search {
    flex: 1;
  }
  .list {
    overflow-y: auto;
    flex: 1;
    display: flex;
    flex-direction: column;
    gap: 3px;
  }
  .hint {
    color: var(--muted);
    padding: 16px;
    text-align: center;
  }
  .crow {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 4px 6px;
    border-radius: var(--r-sm);
    border: 1px solid transparent;
  }
  .crow:hover {
    background: var(--surface-2);
  }
  .crow.restricted {
    border-color: var(--line);
    background: var(--warn-dim);
  }
  .crow img,
  .noimg {
    width: 26px;
    height: 38px;
    object-fit: cover;
    border-radius: var(--r-sm);
    background: var(--surface-3);
    flex: none;
  }
  .cname {
    flex: 1;
    font-size: 13px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .seg {
    display: flex;
    gap: 3px;
    flex: none;
  }
  .sbtn {
    width: 26px;
    height: 26px;
    padding: 0;
    font-size: 12px;
    font-weight: 700;
    background: var(--surface-2);
    color: var(--muted);
    border: 1px solid var(--line);
  }
  .sbtn.on.s0 {
    background: var(--danger); color: #1a0c0c; border-color: transparent;
  }
  .sbtn.on.s1 {
    background: var(--secondary); color: var(--bg); border-color: transparent;
  }
  .sbtn.on.s2 {
    background: var(--accent); color: var(--accent-ink); border-color: transparent;
  }
  .sbtn.on.s3 {
    background: var(--success); color: #0c1a0f; border-color: transparent;
  }

  .bname {
    font-size: 16px;
    font-weight: 700;
    margin-bottom: 10px;
  }
  .from {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 12px;
    color: var(--muted);
    margin-bottom: 10px;
  }
  .from select {
    flex: 1;
  }
  .tally {
    display: flex;
    gap: 10px;
    margin-bottom: 8px;
    font-size: 12px;
    font-weight: 700;
  }
  .t.f {
    color: var(--danger);
  }
  .t.l {
    color: var(--secondary);
  }
  .t.s {
    color: var(--accent);
  }
  .entries {
    overflow-y: auto;
    flex: 1;
    min-height: 60px;
    display: flex;
    flex-direction: column;
    gap: 3px;
  }
  .erow {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 12px;
  }
  .badge {
    font-size: 10px;
    font-weight: 700;
    border-radius: var(--r-sm);
    padding: 2px 6px;
    flex: none;
    width: 62px;
    text-align: center;
  }
  .b0 {
    background: var(--danger-dim); color: var(--danger);
  }
  .b1 {
    background: color-mix(in srgb, var(--secondary) 20%, transparent); color: var(--secondary);
  }
  .b2 {
    background: var(--warn-dim); color: var(--accent);
  }
  .en {
    flex: 1;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .rm {
    width: 22px;
    height: 22px;
    padding: 0;
    font-size: 13px;
    line-height: 1;
  }
  .actions {
    display: flex;
    gap: 8px;
    margin-top: 12px;
  }
  .saved {
    margin-top: 8px;
    font-size: 11px;
    color: var(--success);
  }
  code {
    color: var(--accent);
  }
</style>
