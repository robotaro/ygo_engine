<script>
  // "My Decks": manage the decks you own. Create a new one at any time, edit or
  // delete the ones you've built. Every deck is built only from cards you own.
  import { profile, refreshProfile } from './store.js'
  import DeckBuilder from './DeckBuilder.svelte'
  import { prettyDeckName } from './util.js'

  let { onPlay = null } = $props()

  // `?new` deep-links straight into a fresh build (handy for screenshots/links).
  let editing = $state(
    new URLSearchParams(location.search).get('new') !== null ? { id: null } : null,
  ) // null | { id: string | null }  (id === null => brand-new deck)
  let confirmId = $state('') // deck id awaiting delete confirmation

  let decks = $derived($profile?.decks ?? [])

  function newDeck() {
    editing = { id: null }
  }
  function edit(id) {
    editing = { id }
  }
  async function onSaved() {
    await refreshProfile()
    editing = null
  }
  async function del(id) {
    await fetch('/api/decks/' + id, { method: 'DELETE' })
    confirmId = ''
    await refreshProfile()
  }
</script>

{#if editing}
  <div class="editor">
    <button class="back" onclick={() => (editing = null)}>← My Decks</button>
    <DeckBuilder
      ownedOnly
      loadId={editing.id}
      onSaved={onSaved}
      onPlay={(id) => onPlay?.(id)}
    />
  </div>
{:else}
  <div class="mydecks">
    <div class="head">
      <h2>Your decks</h2>
      <button class="new btn-primary" onclick={newDeck}>＋ New Deck</button>
    </div>

    {#if decks.length === 0}
      <div class="empty">No decks yet.</div>
    {:else}
      <div class="list">
        {#each decks as d (d.id)}
          <div class="deck">
            <div class="meta">
              <div class="name">
                {prettyDeckName(d.name)}
                {#if d.isStarter}<span class="tag">Starter</span>{/if}
              </div>
              <div class="sub">
                main {d.main} · extra {d.extra} ·
                <span class:bad={!d.legal}>{d.legal ? 'legal' : 'not legal'}</span>
                · {d.playablePct}% playable
                {#if !d.owned}<span class="bad"> · missing cards</span>{/if}
              </div>
            </div>
            <div class="actions">
              <button class="btn-primary" onclick={() => onPlay?.(d.id)}>Play ▶</button>
              <button onclick={() => edit(d.id)}>Edit</button>
              {#if !d.isStarter}
                {#if confirmId === d.id}
                  <button class="danger" onclick={() => del(d.id)}>Confirm?</button>
                  <button class="btn-ghost" onclick={() => (confirmId = '')}>✕</button>
                {:else}
                  <button class="btn-ghost" onclick={() => (confirmId = d.id)}>Delete</button>
                {/if}
              {/if}
            </div>
          </div>
        {/each}
      </div>
    {/if}
    <p class="hint">Decks are built only from cards in your library. Win duels and open packs to grow it.</p>
  </div>
{/if}

<style>
  .mydecks,
  .editor {
    grid-column: 1 / -1;
    display: flex;
    flex-direction: column;
    min-height: 0;
    height: calc(100vh - 90px);
  }
  .editor {
    gap: 10px;
  }
  .back {
    align-self: flex-start;
    background: transparent;
    color: var(--muted);
    border-color: var(--line);
  }
  .head {
    display: flex;
    align-items: center;
    margin-bottom: 16px;
  }
  h2 {
    margin: 0;
    color: var(--text);
  }
  .new {
    margin-left: auto;
  }
  .empty {
    color: var(--muted);
    padding: 30px;
    text-align: center;
  }
  .list {
    display: flex;
    flex-direction: column;
    gap: 10px;
    overflow-y: auto;
    flex: 1;
  }
  .deck {
    display: flex;
    align-items: center;
    gap: 14px;
    background: var(--surface);
    border: 1px solid var(--line);
    border-radius: var(--r-lg);
    padding: 12px 16px;
  }
  .meta {
    min-width: 0;
  }
  .name {
    font-weight: 700;
    color: var(--text);
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .tag {
    font-size: 10px;
    font-weight: 800;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    color: var(--accent);
    background: var(--surface-2);
    border: 1px solid var(--line);
    padding: 1px 7px;
    border-radius: var(--r-pill);
  }
  .sub {
    font-size: 12px;
    color: var(--muted);
    margin-top: 3px;
  }
  .bad {
    color: var(--danger);
  }
  .actions {
    margin-left: auto;
    display: flex;
    gap: 6px;
    flex: none;
  }
  .danger {
    background: var(--danger);
    color: #fff;
  }
  .hint {
    margin-top: 14px;
    font-size: 12px;
    color: var(--faint);
  }
</style>
