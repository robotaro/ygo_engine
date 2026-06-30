<script>
  // A deck editor over the card pool. Three columns: search/pool · selected-card
  // detail · your deck (with live v6.0 validation).
  //   click a card  -> inspect it (read its effect) in the detail panel
  //   '+' / dbl-clik -> add it to the deck
  let { onPlay = null, onSaved = null } = $props()

  let name = $state('My Deck')
  let query = $state('')
  let typeFilter = $state('') // '' | monster | spell | trap
  let functionalOnly = $state(false) // off by default, or spells/traps vanish
  let results = $state([])
  let loading = $state(false)
  let selected = $state(null) // the card shown in the detail panel

  // The deck: card name -> count, split by where the card lives.
  let main = $state({})
  let extra = $state({})
  let known = $state({}) // name -> full card object (for rendering the deck list)

  let validation = $state(null)
  let saving = $state(false)
  let savedId = $state(null)

  let formats = $state([]) // Forbidden/Limited lists to validate against
  let format = $state('none')

  const MAX_COPIES = 3

  let mainSize = $derived(Object.values(main).reduce((a, b) => a + b, 0))
  let extraSize = $derived(Object.values(extra).reduce((a, b) => a + b, 0))
  // name -> {cap,count,ok} for cards the active banlist restricts (inline flags)
  let restrictedMap = $derived(
    Object.fromEntries((validation?.restricted || []).map((r) => [r.name, r])),
  )

  // Load the available formats once.
  $effect(() => {
    fetch('/api/formats')
      .then((r) => r.json())
      .then((d) => (formats = d.formats))
      .catch(() => {})
  })

  function banLabel(cap) {
    return cap === 0 ? 'Forbidden' : cap === 1 ? 'Limit 1' : 'Semi 2'
  }

  function copies(cardName) {
    return (main[cardName] || 0) + (extra[cardName] || 0)
  }

  function add(card) {
    if (!card || copies(card.name) >= MAX_COPIES) return
    known = { ...known, [card.name]: card }
    if (card.extraDeck) extra = { ...extra, [card.name]: (extra[card.name] || 0) + 1 }
    else main = { ...main, [card.name]: (main[card.name] || 0) + 1 }
  }

  function remove(cardName, bucketName) {
    const bucket = bucketName === 'extra' ? { ...extra } : { ...main }
    if (!bucket[cardName]) return
    bucket[cardName] -= 1
    if (bucket[cardName] <= 0) delete bucket[cardName]
    if (bucketName === 'extra') extra = bucket
    else main = bucket
  }

  function clearDeck() {
    main = {}
    extra = {}
    savedId = null
  }

  // -- card search (debounced) --
  $effect(() => {
    const q = query
    const t = typeFilter
    const f = functionalOnly
    loading = true
    const handle = setTimeout(async () => {
      const params = new URLSearchParams({ limit: '150' })
      if (q) params.set('query', q)
      if (t) params.set('type', t)
      if (f) params.set('functional', 'true')
      try {
        const res = await fetch(`/api/cards?${params}`)
        const data = await res.json()
        results = data.cards
      } catch {
        results = []
      } finally {
        loading = false
      }
    }, 200)
    return () => clearTimeout(handle)
  })

  // -- live validation (debounced) whenever the deck, its name, or format changes --
  $effect(() => {
    const payload = { name, main: { ...main }, extra: { ...extra }, format }
    if (mainSize === 0 && extraSize === 0) {
      validation = null
      return
    }
    const handle = setTimeout(async () => {
      try {
        const res = await fetch('/api/decks/validate', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        })
        validation = await res.json()
      } catch {
        validation = null
      }
    }, 250)
    return () => clearTimeout(handle)
  })

  async function save() {
    saving = true
    try {
      const res = await fetch('/api/decks', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, main: { ...main }, extra: { ...extra }, format }),
      })
      const data = await res.json()
      savedId = data.id
      onSaved?.(data.id)
    } finally {
      saving = false
    }
  }

  async function saveAndPlay() {
    await save()
    if (savedId) onPlay?.(savedId)
  }

  function img(card) {
    return card?.imageId ? `/cards/${card.imageId}.jpg` : null
  }

  function typeLine(c) {
    if (!c) return ''
    if (c.cardType === 'monster') {
      const bits = []
      if (c.attribute) bits.push(c.attribute)
      if (c.level != null) bits.push(`Level ${c.level}`)
      if (c.race) bits.push(c.race)
      return bits.join(' · ')
    }
    const kind = c.cardType.charAt(0).toUpperCase() + c.cardType.slice(1)
    return c.subtype ? `${kind} · ${c.subtype}` : kind
  }
</script>

<div class="builder">
  <!-- Pool browser -->
  <section class="pool">
    <div class="poolbar">
      <input class="search" placeholder="Search name or text…" bind:value={query} />
      <select bind:value={typeFilter}>
        <option value="">All types</option>
        <option value="monster">Monsters</option>
        <option value="spell">Spells</option>
        <option value="trap">Traps</option>
      </select>
      <label class="chk" title="Only cards whose effect is implemented (hides most Spells/Traps for now)">
        <input type="checkbox" bind:checked={functionalOnly} /> implemented only
      </label>
    </div>
    <div class="grid">
      {#if loading}
        <div class="hint">Searching…</div>
      {:else if results.length === 0}
        <div class="hint">No cards match.</div>
      {:else}
        {#each results as card (card.name)}
          {@const n = copies(card.name)}
          <div
            class="poolcard"
            class:sel={selected?.name === card.name}
            title={card.name}
            role="button"
            tabindex="0"
            onclick={() => (selected = card)}
            ondblclick={() => add(card)}
            onkeydown={(e) => e.key === 'Enter' && (selected = card)}
          >
            <div class="thumb">
              {#if img(card)}
                <img
                  src={img(card)}
                  alt={card.name}
                  loading="lazy"
                  decoding="async"
                  onerror={(e) => (e.currentTarget.style.display = 'none')}
                />
              {/if}
              {#if !card.functional}<span class="dead" title="Effect not implemented yet">∅</span>{/if}
              {#if n > 0}<span class="owned">{n}</span>{/if}
              <button
                class="plus"
                title="Add to deck"
                disabled={n >= MAX_COPIES}
                onclick={(e) => {
                  e.stopPropagation()
                  add(card)
                }}>＋</button
              >
            </div>
            <div class="label">
              <div class="cn">{card.name}</div>
              {#if card.cardType === 'monster'}
                <div class="st">{card.attack ?? '?'} / {card.defense ?? '?'}</div>
              {:else}
                <div class="st">{card.subtype || card.cardType}</div>
              {/if}
            </div>
          </div>
        {/each}
      {/if}
    </div>
  </section>

  <!-- Selected-card detail -->
  <section class="detail">
    {#if selected}
      <div class="dart">
        {#if img(selected)}
          <img src={img(selected)} alt={selected.name} decoding="async" />
        {:else}
          <div class="noart">{selected.name}</div>
        {/if}
      </div>
      <h3>{selected.name}</h3>
      <div class="dmeta">{typeLine(selected)}</div>
      {#if selected.cardType === 'monster'}
        <div class="dstats">
          ATK <b>{selected.attack ?? '?'}</b> · DEF <b>{selected.defense ?? '?'}</b>
        </div>
      {/if}
      {#if !selected.functional}
        <div class="dflag">⚠ Effect not implemented yet — plays as a vanilla card for now.</div>
      {/if}
      <p class="dtext">{selected.text || '(no card text)'}</p>
      <button
        class="addbtn btn-primary"
        disabled={copies(selected.name) >= MAX_COPIES}
        onclick={() => add(selected)}
      >
        ＋ Add to Deck ({copies(selected.name)}/{MAX_COPIES})
      </button>
    {:else}
      <div class="dempty">
        <p>Click a card to read its effect.</p>
        <p class="tip">Double-click or the ＋ button adds it to your deck.</p>
      </div>
    {/if}
  </section>

  <!-- Current deck -->
  <section class="deck">
    <input class="deckname" bind:value={name} />

    <label class="fmtrow">
      <span>Format</span>
      <select bind:value={format}>
        {#each formats as f (f.id)}
          <option value={f.id}>{f.name}{f.restricted ? ` (${f.restricted})` : ''}</option>
        {/each}
      </select>
    </label>

    <div class="counts">
      <span class="csize" class:bad={mainSize < 40 || mainSize > 60}>Main {mainSize}/40–60</span>
      <span class="csize" class:bad={extraSize > 15}>Extra {extraSize}/15</span>
    </div>

    {#if validation}
      <div class="verdict" class:ok={validation.legal}>
        {validation.legal ? '✓ Legal' : '✗ Illegal'} · {validation.playablePct}% playable
      </div>
      {#each validation.errors as e}<div class="err">✗ {e}</div>{/each}
      {#each validation.warnings as w}<div class="warn">⚠ {w}</div>{/each}
    {:else}
      <div class="verdict empty">Add cards to build a deck.</div>
    {/if}

    <div class="decklists">
      <h4>Main Deck ({mainSize})</h4>
      {#each Object.entries(main) as [cn, count] (cn)}
        <div class="row">
          <span class="x">{count}×</span>
          <button class="rn" onclick={() => (selected = known[cn])}>{cn}</button>
          {#if restrictedMap[cn]}
            <span class="ban" class:over={!restrictedMap[cn].ok}>{banLabel(restrictedMap[cn].cap)}</span>
          {/if}
          <button class="mini" onclick={() => add(known[cn])} disabled={copies(cn) >= MAX_COPIES}
            >+</button
          >
          <button class="mini" onclick={() => remove(cn, 'main')}>−</button>
        </div>
      {/each}

      {#if extraSize > 0}
        <h4>Extra Deck ({extraSize})</h4>
        {#each Object.entries(extra) as [cn, count] (cn)}
          <div class="row">
            <span class="x">{count}×</span>
            <button class="rn" onclick={() => (selected = known[cn])}>{cn}</button>
            {#if restrictedMap[cn]}
              <span class="ban" class:over={!restrictedMap[cn].ok}>{banLabel(restrictedMap[cn].cap)}</span>
            {/if}
            <button class="mini" onclick={() => add(known[cn])} disabled={copies(cn) >= MAX_COPIES}
              >+</button
            >
            <button class="mini" onclick={() => remove(cn, 'extra')}>−</button>
          </div>
        {/each}
      {/if}
    </div>

    <div class="deckactions">
      <button onclick={save} disabled={saving || mainSize === 0}>
        {saving ? 'Saving…' : 'Save Deck'}
      </button>
      <button
        class="play btn-primary"
        onclick={saveAndPlay}
        disabled={saving || !validation?.legal}
        title={validation?.legal ? 'Save and duel with this deck' : 'Deck must be legal to play'}
      >
        Save &amp; Play ▶
      </button>
      <button class="btn-ghost" onclick={clearDeck} disabled={mainSize === 0 && extraSize === 0}
        >Clear</button
      >
    </div>
    {#if savedId}<div class="saved">Saved as <code>{savedId}</code></div>{/if}
  </section>
</div>

<style>
  .builder {
    display: grid;
    grid-template-columns: 1fr minmax(230px, 270px) minmax(300px, 330px);
    gap: 14px;
    height: 100%;
    min-height: 0;
  }
  .pool,
  .detail,
  .deck {
    background: var(--surface);
    border: 1px solid var(--line);
    border-radius: var(--r-lg);
    padding: 12px;
    display: flex;
    flex-direction: column;
    min-height: 0;
  }
  .poolbar {
    display: flex;
    gap: 8px;
    margin-bottom: 10px;
    align-items: center;
  }
  .search {
    flex: 1;
  }
  .chk {
    font-size: 12px;
    color: var(--muted);
    display: flex;
    align-items: center;
    gap: 5px;
    white-space: nowrap;
  }
  .grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(86px, 1fr));
    gap: 8px;
    overflow-y: auto;
    align-content: start;
    flex: 1;
  }
  .hint {
    color: var(--muted);
    padding: 20px;
    grid-column: 1 / -1;
    text-align: center;
  }
  .poolcard {
    display: flex;
    flex-direction: column;
    border-radius: var(--r);
    border: 1px solid var(--line);
    background: var(--surface-2);
    overflow: hidden;
    cursor: pointer;
    color: var(--text);
  }
  .poolcard:hover {
    border-color: var(--accent);
  }
  .poolcard.sel {
    border-color: var(--accent);
    box-shadow: 0 0 0 1px var(--accent);
  }
  /* the image area keeps the real card aspect ratio so nothing is cropped */
  .thumb {
    position: relative;
    width: 100%;
    aspect-ratio: 59 / 86;
    background: var(--surface-3);
  }
  .thumb img {
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
    object-fit: contain;
  }
  /* name + stats live in a strip BELOW the card, never over the art */
  .label {
    padding: 4px 6px 5px;
    background: var(--surface);
    border-top: 1px solid var(--line);
  }
  .cn {
    font-size: 10px;
    font-weight: 700;
    line-height: 1.2;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }
  .st {
    font-size: 10px;
    color: var(--muted);
    margin-top: 2px;
  }
  .owned {
    position: absolute;
    top: 3px;
    left: 3px;
    z-index: 2;
    background: var(--accent);
    color: var(--accent-ink);
    font-weight: 800;
    font-size: 11px;
    border-radius: 50%;
    width: 18px;
    height: 18px;
    display: grid;
    place-items: center;
  }
  .dead {
    position: absolute;
    top: 3px;
    right: 3px;
    z-index: 2;
    color: var(--danger);
    font-weight: 800;
    text-shadow: 0 0 3px #000;
    pointer-events: none;
  }
  .plus {
    position: absolute;
    bottom: 3px;
    right: 3px;
    z-index: 3;
    width: 24px;
    height: 24px;
    padding: 0;
    font-size: 15px;
    line-height: 1;
    border-radius: var(--r-sm);
    background: var(--accent);
    color: var(--accent-ink);
    border: none;
    opacity: 0;
    transition: opacity 0.12s;
  }
  .poolcard:hover .plus {
    opacity: 1;
  }
  .plus:hover {
    background: var(--accent-hover);
  }
  .plus:disabled {
    background: var(--surface-3);
    color: var(--faint);
    opacity: 1;
    cursor: not-allowed;
  }

  /* Detail panel */
  .dart {
    width: 100%;
    aspect-ratio: 59 / 86;
    border-radius: var(--r);
    overflow: hidden;
    border: 1px solid var(--line-strong);
    background: var(--surface-2);
    display: grid;
    place-items: center;
    flex: none;
  }
  .dart img {
    width: 100%;
    height: 100%;
    object-fit: cover;
  }
  .noart {
    font-weight: 700;
    text-align: center;
    padding: 10px;
  }
  .detail h3 {
    margin: 10px 0 2px;
    font-size: 16px;
    color: var(--text);
  }
  .dmeta {
    font-size: 12px;
    color: var(--muted);
  }
  .dstats {
    font-size: 13px;
    margin-top: 4px;
  }
  .dstats b {
    color: var(--text);
  }
  .dflag {
    margin-top: 8px;
    font-size: 11px;
    color: var(--warn);
    background: var(--warn-dim);
    border-radius: var(--r-sm);
    padding: 5px 7px;
  }
  .dtext {
    margin-top: 8px;
    font-size: 12px;
    line-height: 1.5;
    color: var(--text);
    white-space: pre-wrap;
    overflow-y: auto;
    flex: 1;
    min-height: 40px;
  }
  .dempty {
    margin: auto;
    text-align: center;
    color: var(--muted);
  }
  .tip {
    font-size: 11px;
    color: var(--faint);
  }

  /* Deck panel */
  .deckname {
    font-size: 16px;
    font-weight: 700;
    margin-bottom: 8px;
  }
  .fmtrow {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 8px;
    font-size: 12px;
    color: var(--muted);
  }
  .fmtrow select {
    flex: 1;
  }
  .ban {
    font-size: 10px;
    font-weight: 700;
    color: var(--warn);
    background: var(--warn-dim);
    border-radius: var(--r-sm);
    padding: 1px 6px;
    white-space: nowrap;
  }
  .ban.over {
    color: var(--danger);
    background: var(--danger-dim);
  }
  .counts {
    display: flex;
    gap: 10px;
    margin-bottom: 6px;
  }
  .csize {
    font-size: 12px;
    color: var(--success);
  }
  .csize.bad {
    color: var(--danger);
  }
  .verdict {
    font-weight: 700;
    padding: 6px 9px;
    border-radius: var(--r-sm);
    background: var(--danger-dim);
    color: var(--danger);
    margin-bottom: 6px;
  }
  .verdict.ok {
    background: var(--success-dim);
    color: var(--success);
  }
  .verdict.empty {
    background: none;
    color: var(--muted);
    font-weight: 400;
  }
  .err {
    font-size: 11px;
    color: var(--danger);
  }
  .warn {
    font-size: 11px;
    color: var(--warn);
  }
  .decklists {
    overflow-y: auto;
    flex: 1;
    margin: 8px 0;
    min-height: 60px;
  }
  h4 {
    margin: 10px 0 5px;
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--muted);
    border-bottom: 1px solid var(--line);
    padding-bottom: 3px;
  }
  .row {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 12px;
    padding: 1px 0;
  }
  .x {
    color: var(--accent);
    font-weight: 700;
    width: 22px;
  }
  .rn {
    flex: 1;
    text-align: left;
    background: none;
    border: none;
    color: var(--text);
    padding: 2px 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    cursor: pointer;
  }
  .rn:hover {
    background: none;
    color: var(--accent);
  }
  .mini {
    width: 22px;
    height: 22px;
    padding: 0;
    font-size: 14px;
    line-height: 1;
  }
  .deckactions {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
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
