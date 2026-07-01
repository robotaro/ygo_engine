<script>
  // Tournament: enter a gauntlet bracket of duelists with one of your decks.
  // Win every round to be crowned champion for a DP bonus.
  import { profile, startTournamentDuel } from './store.js'
  import { getJSON, postJSON } from './api.js'
  import { prettyDeckName } from './util.js'

  let presets = $state([])
  let run = $state(null) // active/finished run, or null
  let current = $state(null) // opponent you face now
  let deckId = $state('')
  let busy = $state(false)
  let error = $state('')

  let myDecks = $derived($profile?.decks ?? [])

  async function load() {
    try {
      const d = await getJSON('/api/tournaments')
      presets = d.presets
      run = d.tournament
      current = d.currentOpponent
    } catch {
      presets = []
    }
  }
  $effect(() => {
    load()
  })
  $effect(() => {
    if ((!deckId || !myDecks.some((d) => d.id === deckId)) && myDecks.length) {
      const active = $profile?.activeDeck
      deckId = active && myDecks.some((d) => d.id === active) ? active : myDecks[0].id
    }
  })

  async function start(preset) {
    busy = true
    error = ''
    try {
      const d = await postJSON('/api/tournaments/start', { presetId: preset.id, deckId })
      run = d.tournament
      current = d.currentOpponent
    } catch (e) {
      error = typeof e.detail === 'string' ? e.detail : 'Could not start the tournament.'
    } finally {
      busy = false
    }
  }

  function playRound() {
    if (run && current) startTournamentDuel(undefined, run.deck, current.id)
  }

  async function leaveRun() {
    await fetch('/api/tournament/forfeit', { method: 'POST' })
    await load()
  }

  function deckName(id) {
    return prettyDeckName(myDecks.find((d) => d.id === id)?.name || id)
  }
  function status(i) {
    if (!run) return ''
    if (i < run.round) return 'won'
    if (i === run.round && run.active) return 'now'
    return 'next'
  }
</script>

<div class="tourney">
  {#if error}<div class="error">{error}</div>{/if}

  {#if run && (run.active || run.champion || run.eliminated)}
    <!-- An in-progress or just-finished run -->
    <div class="runhead">
      <div>
        <h2>{run.name}</h2>
        <div class="sub">Your deck: {deckName(run.deck)} · reward ◈ {run.reward.toLocaleString()} DP</div>
      </div>
      <button class="btn-ghost" onclick={leaveRun}>
        {run.active ? 'Forfeit' : 'Back to Tournaments'}
      </button>
    </div>

    {#if run.champion}
      <div class="banner champ">🏆 Champion! You won the bracket — <b>+{run.reward.toLocaleString()} DP</b></div>
    {:else if run.eliminated}
      <div class="banner out">Eliminated in round {run.wins + 1}. Better luck next time!</div>
    {/if}

    <div class="bracket">
      {#each run.opponents as o, i (o.id)}
        <div class="seat {status(i)}">
          <div class="avatar">
            {#if o.portrait}<img src={o.portrait} alt={o.name} />{:else}<span>?</span>{/if}
          </div>
          <div class="seatmeta">
            <div class="rnd">Round {i + 1}</div>
            <div class="oname">{o.name}</div>
          </div>
          <div class="mark">
            {#if status(i) === 'won'}✓{:else if status(i) === 'now'}▶{/if}
          </div>
        </div>
      {/each}
    </div>

    {#if run.active && current}
      <div class="play">
        <button class="start btn-primary" onclick={playRound}>
          Play Round {run.wins + 1} vs {current.name} ▶
        </button>
      </div>
    {/if}
  {:else}
    <!-- No active run: choose a championship -->
    <div class="lobby">
      <h2>Tournaments</h2>
      <p class="sub">Win every round of a bracket to be crowned champion for a DP bonus.</p>

      <label class="deckpick">
        <span>Enter with</span>
        <select bind:value={deckId}>
          {#each myDecks as d (d.id)}
            <option value={d.id}>{prettyDeckName(d.name)}{d.legal ? '' : ' ⚠'}</option>
          {/each}
        </select>
      </label>

      <div class="presets">
        {#each presets as p (p.id)}
          <div class="preset">
            <div class="pname">{p.name}</div>
            <div class="pmeta">{p.rounds} rounds · champion ◈ {p.reward.toLocaleString()} DP</div>
            <div class="foes">
              {#each p.opponents as o (o.id)}
                <div class="foe" title={o.name}>
                  {#if o.portrait}<img src={o.portrait} alt={o.name} />{:else}<span>?</span>{/if}
                </div>
              {/each}
            </div>
            <button class="btn-primary enter" disabled={busy || !deckId} onclick={() => start(p)}>
              Enter ▶
            </button>
          </div>
        {/each}
      </div>
    </div>
  {/if}
</div>

<style>
  .tourney {
    grid-column: 1 / -1;
    display: flex;
    flex-direction: column;
    min-height: 0;
    height: calc(100vh - 90px);
    overflow-y: auto;
  }
  h2 {
    margin: 0;
    color: var(--text);
  }
  .sub {
    color: var(--muted);
    font-size: 13px;
    margin: 4px 0 16px;
  }
  .error {
    color: var(--danger);
    background: var(--danger-dim);
    padding: 6px 10px;
    border-radius: var(--r-sm);
    margin-bottom: 10px;
    font-size: 13px;
  }
  .runhead {
    display: flex;
    align-items: flex-start;
    gap: 12px;
    margin-bottom: 12px;
  }
  .runhead button {
    margin-left: auto;
  }
  .banner {
    padding: 12px 16px;
    border-radius: var(--r);
    margin-bottom: 16px;
    font-size: 15px;
  }
  .banner.champ {
    background: var(--accent);
    color: var(--accent-ink);
    font-weight: 700;
  }
  .banner.out {
    background: var(--danger-dim);
    color: var(--danger);
  }
  .bracket {
    display: flex;
    flex-direction: column;
    gap: 8px;
    max-width: 520px;
  }
  .seat {
    display: flex;
    align-items: center;
    gap: 12px;
    background: var(--surface);
    border: 1px solid var(--line);
    border-radius: var(--r);
    padding: 8px 12px;
  }
  .seat.won {
    opacity: 0.6;
  }
  .seat.now {
    border-color: var(--accent);
    box-shadow: 0 0 0 1px var(--accent);
  }
  .avatar,
  .foe {
    width: 40px;
    height: 40px;
    border-radius: 50%;
    overflow: hidden;
    background: var(--surface-3);
    display: grid;
    place-items: center;
    flex: none;
    color: var(--faint);
  }
  .avatar img,
  .foe img {
    width: 100%;
    height: 100%;
    object-fit: cover;
  }
  .seatmeta {
    min-width: 0;
  }
  .rnd {
    font-size: 11px;
    color: var(--muted);
  }
  .oname {
    font-weight: 700;
    color: var(--text);
  }
  .mark {
    margin-left: auto;
    font-weight: 800;
    color: var(--accent);
    font-size: 18px;
  }
  .play {
    margin-top: 18px;
  }
  .start {
    font-size: 15px;
    padding: 11px 22px;
  }
  .deckpick {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-bottom: 18px;
    font-size: 13px;
    color: var(--muted);
  }
  .deckpick select {
    min-width: 220px;
  }
  .presets {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
    gap: 14px;
  }
  .preset {
    background: var(--surface);
    border: 1px solid var(--line);
    border-radius: var(--r-lg);
    padding: 14px;
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  .pname {
    font-weight: 700;
    color: var(--text);
  }
  .pmeta {
    font-size: 12px;
    color: var(--muted);
  }
  .foes {
    display: flex;
    flex-wrap: wrap;
    gap: 5px;
  }
  .foes .foe {
    width: 30px;
    height: 30px;
  }
  .enter {
    margin-top: auto;
  }
</style>
