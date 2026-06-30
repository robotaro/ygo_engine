<script>
  // Build your own Forbidden/Limited list. Search the pool, set each card's
  // status (Forbidden / Limited / Semi / Unlimited), name it, and save — it then
  // shows up as a selectable Format in the Play tab and Deck Builder.
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
    fetch('/api/formats')
      .then((r) => r.json())
      .then((d) => (formats = d.formats.filter((f) => f.id !== 'none')))
      .catch(() => {})
  })

  // Pool search (debounced).
  $effect(() => {
    const q = query
    const t = typeFilter
    loading = true
    const handle = setTimeout(async () => {
      const params = new URLSearchParams({ limit: '150' })
      if (q) params.set('query', q)
      if (t) params.set('type', t)
      try {
        const res = await fetch(`/api/cards?${params}`)
        results = (await res.json()).cards
      } catch {
        results = []
      } finally {
        loading = false
      }
    }, 200)
    return () => clearTimeout(handle)
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
      const res = await fetch('/api/banlist?id=' + encodeURIComponent(id))
      const data = await res.json()
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
      const res = await fetch('/api/banlists', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, limits: { ...limits } }),
      })
      const data = await res.json()
      savedId = data.id
      onSaved?.(data.id)
    } finally {
      saving = false
    }
  }

  function img(card) {
    return card?.imageId ? `/cards/${card.imageId}.jpg` : null
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
            {#if img(card)}
              <img src={img(card)} alt="" loading="lazy" decoding="async" />
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
      <button class="savebtn" onclick={save} disabled={saving || restricted.length === 0}>
        {saving ? 'Saving…' : 'Save Banlist'}
      </button>
      <button class="ghost" onclick={() => (limits = {})} disabled={restricted.length === 0}
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
    background: #14140f;
    border: 1px solid #2c2c2c;
    border-radius: 10px;
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
  input,
  select {
    background: #222;
    border: 1px solid #444;
    color: #eee;
    border-radius: 5px;
    padding: 6px 8px;
  }
  .list {
    overflow-y: auto;
    flex: 1;
    display: flex;
    flex-direction: column;
    gap: 3px;
  }
  .hint {
    color: #888;
    padding: 16px;
    text-align: center;
  }
  .crow {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 3px 6px;
    border-radius: 6px;
    border: 1px solid transparent;
  }
  .crow:hover {
    background: #1d1d24;
  }
  .crow.restricted {
    border-color: #4a3a1a;
    background: rgba(255, 215, 106, 0.05);
  }
  .crow img,
  .noimg {
    width: 26px;
    height: 38px;
    object-fit: cover;
    border-radius: 3px;
    background: #2b2b33;
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
    gap: 2px;
    flex: none;
  }
  .sbtn {
    width: 26px;
    height: 26px;
    padding: 0;
    font-size: 12px;
    font-weight: 700;
    background: #2a2a30;
    color: #aaa;
    border: 1px solid #3a3a45;
  }
  .sbtn.on.s0 {
    background: #b33; color: #fff;
  }
  .sbtn.on.s1 {
    background: #c87f2a; color: #1a1a1a;
  }
  .sbtn.on.s2 {
    background: #b8a23a; color: #1a1a1a;
  }
  .sbtn.on.s3 {
    background: #3a6a3a; color: #fff;
  }

  .bname {
    font-size: 16px;
    font-weight: 700;
    margin-bottom: 8px;
  }
  .from {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 12px;
    color: #bbb;
    margin-bottom: 10px;
  }
  .from select {
    flex: 1;
  }
  .tally {
    display: flex;
    gap: 8px;
    margin-bottom: 8px;
    font-size: 12px;
    font-weight: 700;
  }
  .t.f {
    color: #ff8a7a;
  }
  .t.l {
    color: #ffc06a;
  }
  .t.s {
    color: #ffe08a;
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
    border-radius: 4px;
    padding: 1px 6px;
    flex: none;
    width: 62px;
    text-align: center;
  }
  .b0 {
    background: rgba(255, 107, 107, 0.18); color: #ff8a7a;
  }
  .b1 {
    background: rgba(255, 160, 60, 0.18); color: #ffc06a;
  }
  .b2 {
    background: rgba(255, 215, 106, 0.16); color: #ffe08a;
  }
  .en {
    flex: 1;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .rm {
    width: 20px;
    height: 20px;
    padding: 0;
    background: #333;
    color: #ddd;
    font-size: 13px;
    line-height: 1;
  }
  .actions {
    display: flex;
    gap: 8px;
    margin-top: 10px;
  }
  .savebtn {
    background: #b8923a;
    color: #1a1a1a;
    font-weight: 700;
  }
  .ghost {
    background: #333;
    color: #ddd;
  }
  button:disabled {
    opacity: 0.4;
    cursor: not-allowed;
  }
  .saved {
    margin-top: 8px;
    font-size: 11px;
    color: #9fd9a9;
  }
  code {
    color: #d9bf7a;
  }
</style>
