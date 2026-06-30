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

  const MAX_COPIES = 3

  let mainSize = $derived(Object.values(main).reduce((a, b) => a + b, 0))
  let extraSize = $derived(Object.values(extra).reduce((a, b) => a + b, 0))

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

  // -- live validation (debounced) whenever the deck or its name changes --
  $effect(() => {
    const payload = { name, main: { ...main }, extra: { ...extra } }
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
        body: JSON.stringify({ name, main: { ...main }, extra: { ...extra } }),
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
            {#if img(card)}
              <img
                src={img(card)}
                alt={card.name}
                loading="lazy"
                decoding="async"
                onerror={(e) => e.currentTarget.remove()}
              />
            {/if}
            <div class="cardgloss">
              <div class="cn">{card.name}</div>
              {#if card.cardType === 'monster'}
                <div class="st">{card.attack ?? '?'}/{card.defense ?? '?'}</div>
              {:else}
                <div class="st">{card.subtype || card.cardType}</div>
              {/if}
            </div>
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
        class="addbtn"
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
        class="play"
        onclick={saveAndPlay}
        disabled={saving || !validation?.legal}
        title={validation?.legal ? 'Save and duel with this deck' : 'Deck must be legal to play'}
      >
        Save &amp; Play ▶
      </button>
      <button class="ghost" onclick={clearDeck} disabled={mainSize === 0 && extraSize === 0}
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
    background: #14140f;
    border: 1px solid #2c2c2c;
    border-radius: 10px;
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
  input,
  select {
    background: #222;
    border: 1px solid #444;
    color: #eee;
    border-radius: 5px;
    padding: 6px 8px;
  }
  .chk {
    font-size: 12px;
    color: #bbb;
    display: flex;
    align-items: center;
    gap: 4px;
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
    color: #888;
    padding: 20px;
    grid-column: 1 / -1;
    text-align: center;
  }
  .poolcard {
    position: relative;
    height: 122px;
    border-radius: 7px;
    border: 1px solid #3a3a45;
    background: linear-gradient(160deg, #2b2b33, #1c1c22);
    overflow: hidden;
    cursor: pointer;
    color: #f3f3f3;
  }
  .poolcard:hover {
    border-color: #d9bf7a;
  }
  .poolcard.sel {
    border-color: #6cff9e;
    box-shadow: 0 0 0 1px #6cff9e;
  }
  .poolcard img {
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
    object-fit: cover;
  }
  .cardgloss {
    position: absolute;
    inset: auto 0 0 0;
    background: linear-gradient(transparent, rgba(0, 0, 0, 0.85));
    padding: 10px 4px 3px;
    z-index: 1;
    pointer-events: none;
  }
  .cn {
    font-size: 9px;
    font-weight: 700;
    line-height: 1.1;
    text-shadow: 0 1px 2px #000;
  }
  .st {
    font-size: 9px;
    color: #ffcf8a;
  }
  .owned {
    position: absolute;
    top: 3px;
    left: 3px;
    z-index: 2;
    background: #b8923a;
    color: #1a1a1a;
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
    color: #ff8a7a;
    font-weight: 800;
    text-shadow: 0 0 3px #000;
    pointer-events: none;
  }
  .plus {
    position: absolute;
    bottom: 3px;
    right: 3px;
    z-index: 3;
    width: 22px;
    height: 22px;
    padding: 0;
    font-size: 14px;
    line-height: 1;
    border-radius: 5px;
    background: rgba(184, 146, 58, 0.92);
    color: #1a1a1a;
    opacity: 0;
    transition: opacity 0.12s;
  }
  .poolcard:hover .plus {
    opacity: 1;
  }
  .plus:disabled {
    background: rgba(90, 90, 90, 0.85);
    color: #ccc;
    cursor: not-allowed;
  }

  /* Detail panel */
  .dart {
    width: 100%;
    aspect-ratio: 59 / 86;
    border-radius: 8px;
    overflow: hidden;
    border: 2px solid #4a4a55;
    background: linear-gradient(160deg, #2b2b33, #1c1c22);
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
    color: #ffe08a;
  }
  .dmeta {
    font-size: 12px;
    color: #c4c4cc;
  }
  .dstats {
    font-size: 13px;
    margin-top: 4px;
  }
  .dstats b {
    color: #ffd9a0;
  }
  .dflag {
    margin-top: 8px;
    font-size: 11px;
    color: #ffd76a;
    background: rgba(255, 215, 106, 0.1);
    border-radius: 5px;
    padding: 4px 6px;
  }
  .dtext {
    margin-top: 8px;
    font-size: 12px;
    line-height: 1.5;
    color: #dcdce4;
    white-space: pre-wrap;
    overflow-y: auto;
    flex: 1;
    min-height: 40px;
  }
  .addbtn {
    background: #b8923a;
    color: #1a1a1a;
    font-weight: 700;
  }
  .addbtn:disabled {
    opacity: 0.4;
    cursor: not-allowed;
  }
  .dempty {
    margin: auto;
    text-align: center;
    color: #888;
  }
  .tip {
    font-size: 11px;
    color: #666;
  }

  /* Deck panel */
  .deckname {
    font-size: 16px;
    font-weight: 700;
    margin-bottom: 8px;
  }
  .counts {
    display: flex;
    gap: 10px;
    margin-bottom: 6px;
  }
  .csize {
    font-size: 12px;
    color: #9fd9a9;
  }
  .csize.bad {
    color: #ff8a7a;
  }
  .verdict {
    font-weight: 700;
    padding: 5px 8px;
    border-radius: 6px;
    background: rgba(255, 107, 107, 0.15);
    color: #ff9e8a;
    margin-bottom: 6px;
  }
  .verdict.ok {
    background: rgba(108, 255, 158, 0.14);
    color: #8dff9e;
  }
  .verdict.empty {
    background: none;
    color: #888;
    font-weight: 400;
  }
  .err {
    font-size: 11px;
    color: #ff9e8a;
  }
  .warn {
    font-size: 11px;
    color: #ffd76a;
  }
  .decklists {
    overflow-y: auto;
    flex: 1;
    margin: 8px 0;
    min-height: 60px;
  }
  h4 {
    margin: 8px 0 4px;
    font-size: 12px;
    color: #d9bf7a;
    border-bottom: 1px solid #2c2c2c;
    padding-bottom: 2px;
  }
  .row {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 12px;
    padding: 1px 0;
  }
  .x {
    color: #ffcf8a;
    font-weight: 700;
    width: 22px;
  }
  .rn {
    flex: 1;
    text-align: left;
    background: none;
    color: #eee;
    padding: 2px 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    cursor: pointer;
  }
  .rn:hover {
    color: #6cff9e;
  }
  .mini {
    width: 20px;
    height: 20px;
    padding: 0;
    font-size: 13px;
    line-height: 1;
    background: #333;
    color: #eee;
  }
  .mini:hover {
    background: #555;
  }
  .deckactions {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
  }
  .play {
    background: #2a8a4a;
    color: #fff;
  }
  .play:hover {
    background: #36a85c;
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
