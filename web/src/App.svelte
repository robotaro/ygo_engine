<script>
  import { onMount } from 'svelte'
  import CardTile from './lib/CardTile.svelte'
  import {
    board,
    legal,
    responsePrompt,
    targetRequest,
    awaiting,
    logs,
    result,
    connected,
    newGame,
    sendIntent,
  } from './lib/store.js'

  let draggedIid = null
  let selectedAttacker = null
  let pendingTribute = null // {iid, zoneIndex, needed, chosen[], mode}
  let pendingTarget = null // {iid, zoneIndex, candidates[], needed, chosen[]}
  let targetChosen = [] // accumulating clicks for an engine-driven target prompt
  let seedInput = ''

  onMount(() => newGame())

  // reactive views
  $: you = $board?.you
  $: opp = $board?.opponent
  $: phase = $board?.phase
  $: yourTurn = $awaiting
  $: dragging = draggedIid != null
  $: draggingMonster = draggedIid != null && !!summonOptions(draggedIid)
  $: draggingSpellTrap = draggedIid != null && (canActivate(draggedIid) || canSet(draggedIid))
  $: draggingFieldSpell = draggedIid != null && isFieldSpell(draggedIid) && canActivate(draggedIid)
  $: if (phase !== 'battle_phase') selectedAttacker = null
  $: validTargets =
    selectedAttacker != null && $legal ? attackTargets(selectedAttacker) || [] : []
  $: mustDiscard = !!$legal?.discards?.length
  $: pendingName = pendingTribute
    ? (you?.hand.find((c) => c.iid === pendingTribute.iid)?.name ?? 'monster')
    : ''
  $: engineTargets = $targetRequest ? $targetRequest.candidates : []
  $: if (!$targetRequest) targetChosen = []
  $: targetCandidates = pendingTarget
    ? pendingTarget.candidates
    : $targetRequest
      ? engineTargets
      : []
  $: pendingTargetName = pendingTarget
    ? (you?.hand.find((c) => c.iid === pendingTarget.iid)?.name ?? 'spell')
    : ''

  const PHASE_LABEL = {
    draw_phase: 'Draw',
    standby_phase: 'Standby',
    main_phase_1: 'Main 1',
    battle_phase: 'Battle',
    main_phase_2: 'Main 2',
    end_phase: 'End',
  }
  const NEXT_LABEL = {
    main_phase_1: 'Go to Battle ▶',
    battle_phase: 'End Battle ▶',
    main_phase_2: 'End Turn ▶',
  }

  // affordance lookups
  function summonOptions(iid) {
    return $legal?.summonable?.[String(iid)] || null
  }
  function attackTargets(iid) {
    return $legal?.attackers?.[String(iid)] || null
  }
  function activateOptions(iid) {
    return $legal?.activatable?.[String(iid)] || null // [[target iids]...]
  }
  function canActivate(iid) {
    return !!activateOptions(iid)
  }
  function canSet(iid) {
    return $legal?.settable?.includes(iid)
  }
  function firstEmptySpellZone() {
    const z = you?.spellTrapZones || []
    const i = z.findIndex((s) => s === null)
    return i < 0 ? null : i
  }
  function canFlip(iid) {
    return $legal?.flips?.includes(iid)
  }
  function canChangePos(iid) {
    return $legal?.positionChanges?.includes(iid)
  }
  function firstEmptyZone() {
    const z = you?.monsterZones || []
    const i = z.findIndex((s) => s === null)
    return i < 0 ? null : i
  }
  function isDefense(slot) {
    return slot?.position?.includes('defense')
  }

  // interactions
  function onDropSummon(e, zoneIndex) {
    e.preventDefault()
    if (!yourTurn || draggedIid == null) return
    const iid = draggedIid
    draggedIid = null
    const opts = summonOptions(iid)
    if (!opts) return
    if (opts.summon.some((c) => c.length === 0)) {
      sendIntent({ kind: 'summon', iid, tributes: [], zoneIndex })
    } else if (opts.summon.length) {
      pendingTribute = { iid, zoneIndex, needed: opts.summon[0].length, chosen: [], mode: 'summon' }
    }
  }

  function onDropSpellTrap(e, zoneIndex) {
    e.preventDefault()
    if (!yourTurn || draggedIid == null) return
    const iid = draggedIid
    draggedIid = null
    if (canActivate(iid)) beginActivate(iid, zoneIndex)
    else if (canSet(iid)) sendIntent({ kind: 'set', iid, zoneIndex }) // Traps are Set face-down
  }

  function activateSpell(iid) {
    beginActivate(iid, firstEmptySpellZone())
  }

  function setCard(iid) {
    if (canSet(iid)) sendIntent({ kind: 'set', iid, zoneIndex: firstEmptySpellZone() })
  }

  // chain response window
  function respondWith(option) {
    sendIntent({ kind: 'respond', iid: option.iid, targets: option.targets })
  }
  function respondPass() {
    sendIntent({ kind: 'pass' })
  }

  // engine-driven target prompt (forced effects, e.g. Man-Eater Bug)
  function chooseEngineTarget(iid) {
    const tr = $targetRequest
    if (!tr || !tr.candidates.includes(iid) || targetChosen.includes(iid)) return
    const chosen = [...targetChosen, iid]
    if (chosen.length >= tr.count) {
      sendIntent({ kind: 'target', targets: chosen })
      targetChosen = []
    } else {
      targetChosen = chosen
    }
  }

  function beginActivate(iid, zoneIndex) {
    const opts = activateOptions(iid)
    if (!opts) return
    if (opts.some((t) => t.length === 0)) {
      sendIntent({ kind: 'activate', iid, targets: [], zoneIndex }) // no target needed
      return
    }
    const candidates = [...new Set(opts.flat())]
    pendingTarget = { iid, zoneIndex, candidates, needed: opts[0].length, chosen: [] }
  }

  function chooseTarget(iid) {
    const pt = pendingTarget
    if (!pt || !pt.candidates.includes(iid) || pt.chosen.includes(iid)) return
    const chosen = [...pt.chosen, iid]
    if (chosen.length >= pt.needed) {
      sendIntent({ kind: 'activate', iid: pt.iid, targets: chosen, zoneIndex: pt.zoneIndex })
      pendingTarget = null
    } else {
      pendingTarget = { ...pt, chosen }
    }
  }

  function onSet(iid) {
    if (!yourTurn) return
    const opts = summonOptions(iid)
    if (!opts || !opts.set?.length) return
    const zoneIndex = firstEmptyZone()
    if (opts.set.some((c) => c.length === 0)) {
      sendIntent({ kind: 'set', iid, tributes: [], zoneIndex })
    } else {
      pendingTribute = { iid, zoneIndex, needed: opts.set[0].length, chosen: [], mode: 'set' }
    }
  }

  function toggleTribute(iid) {
    const pt = pendingTribute
    const chosen = pt.chosen.includes(iid)
      ? pt.chosen.filter((x) => x !== iid)
      : [...pt.chosen, iid]
    pendingTribute = { ...pt, chosen }
    if (chosen.length === pt.needed) {
      sendIntent({ kind: pt.mode, iid: pt.iid, tributes: chosen, zoneIndex: pt.zoneIndex })
      pendingTribute = null
    }
  }

  function onClickOwnMonster(iid) {
    if (!yourTurn) return
    if ($targetRequest) {
      chooseEngineTarget(iid)
      return
    }
    if (pendingTarget) {
      chooseTarget(iid)
      return
    }
    if (pendingTribute) {
      toggleTribute(iid)
      return
    }
    if (phase === 'battle_phase') {
      if (attackTargets(iid)) selectedAttacker = selectedAttacker === iid ? null : iid
      return
    }
    if (canFlip(iid)) sendIntent({ kind: 'flip', iid })
    else if (canChangePos(iid)) sendIntent({ kind: 'changePosition', iid })
  }

  function onClickOppMonster(iid) {
    if (!yourTurn) return
    if ($targetRequest) {
      chooseEngineTarget(iid)
      return
    }
    if (pendingTarget) {
      chooseTarget(iid)
      return
    }
    if (phase !== 'battle_phase' || selectedAttacker == null) return
    if (validTargets.includes(iid)) {
      sendIntent({ kind: 'attack', attacker: selectedAttacker, target: iid })
      selectedAttacker = null
    }
  }

  function onDirectAttack() {
    if (!yourTurn || phase !== 'battle_phase' || selectedAttacker == null) return
    if (validTargets.includes(null)) {
      sendIntent({ kind: 'attack', attacker: selectedAttacker, target: null })
      selectedAttacker = null
    }
  }

  // A Graveyard card may be a target (Monster Reborn picks either GY; Call of
  // the Haunted picks your own) for the active activation/forced-effect prompt.
  function onClickGraveyard(iid) {
    if (!yourTurn) return
    if ($targetRequest) chooseEngineTarget(iid)
    else if (pendingTarget) chooseTarget(iid)
  }

  // A Spell/Trap card may be a target (e.g. Mystical Space Typhoon hits either
  // player's), or — for your own Set Continuous Trap — something to activate.
  function onClickOwnSpellTrap(iid, zoneIndex) {
    if (!yourTurn) return
    if ($targetRequest) return chooseEngineTarget(iid)
    if (pendingTarget) return chooseTarget(iid)
    if (canActivate(iid)) beginActivate(iid, zoneIndex)
  }

  function onClickOppSpellTrap(iid) {
    if (!yourTurn) return
    if ($targetRequest) chooseEngineTarget(iid)
    else if (pendingTarget) chooseTarget(iid)
  }

  function isFieldSpell(iid) {
    const c = you?.hand.find((x) => x.iid === iid)
    return c?.subtype === 'Field'
  }

  // The Field Zone holds a Field Spell; it can also be a target (Mystical Space
  // Typhoon hits Field Spells too).
  function onClickFieldZone(slot) {
    if (!yourTurn || !slot) return
    if ($targetRequest) chooseEngineTarget(slot.iid)
    else if (pendingTarget) chooseTarget(slot.iid)
  }

  function onDropField(e) {
    e.preventDefault()
    if (!yourTurn || draggedIid == null) return
    const iid = draggedIid
    draggedIid = null
    if (isFieldSpell(iid) && canActivate(iid)) beginActivate(iid, null) // engine routes it to the Field Zone
  }

  function onHandClick(iid) {
    if (mustDiscard) sendIntent({ kind: 'discard', iid })
  }

  function nextPhase() {
    selectedAttacker = null
    pendingTribute = null
    pendingTarget = null
    sendIntent({ kind: 'pass' })
  }

  function startGame() {
    const seed = seedInput.trim() === '' ? undefined : Number(seedInput)
    newGame(seed)
  }
</script>

<main>
  <header>
    <h1>遊 ygo_engine</h1>
    <div class="conn" class:on={$connected}>{$connected ? 'connected' : 'offline'}</div>
    <input placeholder="seed (optional)" bind:value={seedInput} />
    <button onclick={startGame}>New Duel</button>
  </header>

  {#if !$board}
    <div class="placeholder">Connecting to the duel server…</div>
  {:else}
    <div class="table">
      <!-- Opponent -->
      <div
        class="playerbar opp"
        class:targetable={selectedAttacker != null && validTargets.includes(null)}
        onclick={onDirectAttack}
      >
        <div class="who">{opp.name}</div>
        <div class="lp">LP {opp.lifePoints}</div>
        <div class="piles">hand {opp.handCount} · deck {opp.deckCount} · GY {opp.graveyard.length}</div>
        <div class="ohand">
          {#each Array(opp.handCount) as _}<div class="minicard back"></div>{/each}
        </div>
      </div>

      <div class="fieldrow">
        <span class="fieldlabel">Field</span>
        <div
          class="slot field"
          class:targetable={opp.fieldZone && targetCandidates.includes(opp.fieldZone.iid)}
          onclick={() => onClickFieldZone(opp.fieldZone)}
        >
          <CardTile card={opp.fieldZone} small />
        </div>
      </div>

      <div class="zonerow">
        {#each opp.spellTrapZones as slot}
          <div
            class="slot st"
            class:targetable={slot && targetCandidates.includes(slot.iid)}
            onclick={() => slot && onClickOppSpellTrap(slot.iid)}
          >
            <CardTile card={slot} faceDown={slot?.faceDown} small />
          </div>
        {/each}
      </div>
      <div class="zonerow">
        {#each opp.monsterZones as slot}
          <div
            class="slot mon"
            class:targetable={slot &&
              ((selectedAttacker != null && validTargets.includes(slot.iid)) ||
                targetCandidates.includes(slot.iid))}
            onclick={() => slot && onClickOppMonster(slot.iid)}
          >
            <CardTile card={slot} faceDown={slot?.faceDown} defense={isDefense(slot)} small />
          </div>
        {/each}
      </div>

      {#if opp.graveyard.length}
        <div class="gyrow opp">
          <span class="gylabel">Graveyard</span>
          {#each opp.graveyard as gy}
            <div
              class="gycard"
              class:targetable={targetCandidates.includes(gy.iid)}
              onclick={() => onClickGraveyard(gy.iid)}
            >
              <CardTile card={gy} small />
            </div>
          {/each}
        </div>
      {/if}

      <!-- Center status -->
      <div class="status">
        <span class="turn">Turn {$board.turnCount}</span>
        <span class="phase">{PHASE_LABEL[phase] ?? phase}</span>
        <span class="whose">{yourTurn ? 'Your move' : '… opponent thinking'}</span>
        {#if yourTurn && $legal?.canPass}
          <button class="next" onclick={nextPhase}>{NEXT_LABEL[phase] ?? 'Continue ▶'}</button>
        {/if}
      </div>

      {#if $board.chain?.length}
        <div class="chainbar">
          ⛓ Chain:
          {#each $board.chain as link, i}{i > 0 ? ' → ' : ' '}{link.name}{/each}
        </div>
      {/if}

      <!-- You -->
      <div class="zonerow">
        {#each you.monsterZones as slot, i}
          {#if slot}
            <div
              class="slot mon own"
              class:selected={selectedAttacker === slot.iid}
              class:tribute={pendingTribute?.chosen.includes(slot.iid)}
              class:targetable={targetCandidates.includes(slot.iid)}
              class:actionable={yourTurn &&
                (attackTargets(slot.iid) ||
                  canFlip(slot.iid) ||
                  canChangePos(slot.iid) ||
                  pendingTribute ||
                  pendingTarget ||
                  $targetRequest)}
              onclick={() => onClickOwnMonster(slot.iid)}
            >
              <CardTile card={slot} defense={isDefense(slot)} small />
            </div>
          {:else}
            <div
              class="slot mon drop"
              class:armed={draggingMonster}
              ondragover={(e) => e.preventDefault()}
              ondrop={(e) => onDropSummon(e, i)}
            >
              <CardTile card={null} small />
            </div>
          {/if}
        {/each}
      </div>
      <div class="zonerow">
        {#each you.spellTrapZones as slot, i}
          {#if slot}
            <div
              class="slot st"
              class:actionable={yourTurn && canActivate(slot.iid)}
              class:targetable={targetCandidates.includes(slot.iid)}
              onclick={() => onClickOwnSpellTrap(slot.iid, i)}
            >
              <CardTile card={slot} small />
            </div>
          {:else}
            <div
              class="slot st drop"
              class:armed={draggingSpellTrap}
              ondragover={(e) => e.preventDefault()}
              ondrop={(e) => onDropSpellTrap(e, i)}
            >
              <CardTile card={null} small />
            </div>
          {/if}
        {/each}
      </div>

      <div class="fieldrow">
        <span class="fieldlabel">Field</span>
        <div
          class="slot field"
          class:drop={!you.fieldZone}
          class:armed={draggingFieldSpell}
          class:targetable={you.fieldZone && targetCandidates.includes(you.fieldZone.iid)}
          ondragover={(e) => e.preventDefault()}
          ondrop={onDropField}
          onclick={() => onClickFieldZone(you.fieldZone)}
        >
          <CardTile card={you.fieldZone} small />
        </div>
      </div>

      {#if you.graveyard.length}
        <div class="gyrow you">
          <span class="gylabel">Graveyard</span>
          {#each you.graveyard as gy}
            <div
              class="gycard"
              class:targetable={targetCandidates.includes(gy.iid)}
              onclick={() => onClickGraveyard(gy.iid)}
            >
              <CardTile card={gy} small />
            </div>
          {/each}
        </div>
      {/if}

      <div class="playerbar you">
        <div class="who">{you.name}</div>
        <div class="lp">LP {you.lifePoints}</div>
        <div class="piles">deck {you.deckCount} · GY {you.graveyard.length}</div>
      </div>

      <!-- Hand -->
      {#if $targetRequest}
        <div class="banner">
          <strong>{$targetRequest.source}</strong> — {$targetRequest.prompt}
          (click a highlighted monster · {targetChosen.length}/{$targetRequest.count})
        </div>
      {:else if pendingTarget}
        <div class="banner">
          <strong>{pendingTargetName}</strong> — click a highlighted target
          ({pendingTarget.chosen.length}/{pendingTarget.needed})
          <button onclick={() => (pendingTarget = null)}>Cancel</button>
        </div>
      {:else if pendingTribute}
        <div class="banner">
          Tribute Summon <strong>{pendingName}</strong> — click
          {pendingTribute.needed} of your monsters to Tribute
          ({pendingTribute.chosen.length}/{pendingTribute.needed})
          <button onclick={() => (pendingTribute = null)}>Cancel</button>
        </div>
      {:else if mustDiscard}
        <div class="banner">Hand over the limit — click a card to discard down to 6.</div>
      {/if}

      <div class="hand">
        {#each you.hand as card}
          {@const opts = summonOptions(card.iid)}
          {@const activatable = canActivate(card.iid)}
          {@const settable = canSet(card.iid)}
          <div
            class="handcard"
            class:dim={yourTurn && !opts && !activatable && !settable && !mustDiscard}
          >
            <div
              draggable={yourTurn && (!!opts || activatable || settable)}
              ondragstart={() => (draggedIid = card.iid)}
              ondragend={() => (draggedIid = null)}
              onclick={() => onHandClick(card.iid)}
            >
              <CardTile {card} />
            </div>
            {#if yourTurn && activatable}
              <button class="setbtn" onclick={() => activateSpell(card.iid)}>Activate</button>
            {:else if yourTurn && settable}
              <button class="setbtn" onclick={() => setCard(card.iid)}>Set</button>
            {:else if yourTurn && opts?.set?.length}
              <button class="setbtn" onclick={() => onSet(card.iid)}>Set</button>
            {/if}
          </div>
        {/each}
      </div>
    </div>

    <aside class="log">
      <h2>Duel Log</h2>
      <div class="loglines">
        {#each $logs as line}<div class="logline">{line}</div>{/each}
      </div>
    </aside>
  {/if}

  {#if $responsePrompt && $awaiting}
    <div class="overlay">
      <div class="resultcard respond">
        <h2>Your response?</h2>
        <p>{$responsePrompt.event}</p>
        <div class="respond-options">
          {#each $responsePrompt.options as opt}
            <button onclick={() => respondWith(opt)}>{opt.label}</button>
          {/each}
          <button class="passbtn" onclick={respondPass}>Pass</button>
        </div>
      </div>
    </div>
  {/if}

  {#if $result}
    <div class="overlay">
      <div class="resultcard" class:win={$result.youWin}>
        <h2>{$result.youWin ? 'You Win!' : $result.winner == null ? 'Draw' : 'You Lose'}</h2>
        <p>{$result.reason}</p>
        <button onclick={startGame}>Play Again</button>
      </div>
    </div>
  {/if}
</main>

<style>
  :global(body) {
    margin: 0;
    background: #14130f;
    color: #eee;
    font-family: system-ui, sans-serif;
  }
  main {
    display: grid;
    grid-template-columns: 1fr 280px;
    grid-template-rows: auto 1fr;
    gap: 12px;
    max-width: 1100px;
    margin: 0 auto;
    padding: 12px;
  }
  header {
    grid-column: 1 / -1;
    display: flex;
    align-items: center;
    gap: 12px;
  }
  h1 {
    font-size: 20px;
    margin: 0;
    color: #d9bf7a;
  }
  .conn {
    font-size: 11px;
    padding: 2px 8px;
    border-radius: 10px;
    background: #5a2a2a;
  }
  .conn.on {
    background: #2a5a32;
  }
  header input {
    margin-left: auto;
    width: 120px;
    padding: 5px;
    background: #222;
    border: 1px solid #444;
    color: #eee;
    border-radius: 5px;
  }
  button {
    background: #b8923a;
    color: #1a1a1a;
    border: none;
    padding: 6px 12px;
    border-radius: 5px;
    font-weight: 700;
    cursor: pointer;
  }
  button:hover {
    background: #d9bf7a;
  }
  .placeholder {
    grid-column: 1/-1;
    padding: 40px;
    text-align: center;
    color: #888;
  }
  .table {
    background: radial-gradient(circle at center, #1f3a2a, #142016);
    border: 1px solid #2c2c2c;
    border-radius: 10px;
    padding: 14px;
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  .playerbar {
    display: flex;
    align-items: center;
    gap: 14px;
    padding: 6px 10px;
    border-radius: 6px;
    background: rgba(0, 0, 0, 0.25);
  }
  .playerbar.targetable {
    outline: 2px solid #ff6b6b;
    cursor: crosshair;
  }
  .who {
    font-weight: 700;
  }
  .lp {
    font-size: 18px;
    font-weight: 800;
    color: #ffe08a;
  }
  .piles {
    font-size: 12px;
    color: #bbb;
  }
  .ohand {
    margin-left: auto;
    display: flex;
    gap: 2px;
  }
  .minicard.back {
    width: 16px;
    height: 24px;
    border-radius: 3px;
    background: repeating-linear-gradient(45deg, #4a3a14, #4a3a14 3px, #5a4a1e 3px, #5a4a1e 6px);
  }
  .zonerow {
    display: flex;
    gap: 8px;
    justify-content: center;
  }
  .slot {
    width: 64px;
    height: 90px;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: 7px;
  }
  .slot.drop.armed {
    outline: 2px dashed #6cff9e;
    background: rgba(108, 255, 158, 0.08);
  }
  .slot.mon.own.actionable {
    cursor: pointer;
  }
  .slot.mon.own.actionable:hover {
    outline: 2px solid #d9bf7a;
  }
  .slot.selected {
    outline: 2px solid #6cff9e;
  }
  .slot.tribute {
    outline: 2px solid #ff9e3d;
  }
  .slot.targetable {
    outline: 2px solid #ff6b6b;
    cursor: crosshair;
  }
  .slot.st.actionable {
    cursor: pointer;
  }
  .slot.st.actionable:hover {
    outline: 2px solid #c9b3ff;
  }
  .fieldrow {
    display: flex;
    align-items: center;
    gap: 8px;
    justify-content: center;
  }
  .fieldlabel {
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 1px;
    color: #8a7fb0;
  }
  .slot.field {
    border: 1px solid #4a3f6a;
  }
  .slot.field.armed {
    outline: 2px dashed #c9b3ff;
    background: rgba(201, 179, 255, 0.08);
  }
  .gyrow {
    display: flex;
    align-items: center;
    gap: 4px;
    justify-content: center;
    flex-wrap: wrap;
    padding: 2px 6px;
    opacity: 0.85;
  }
  .gylabel {
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 1px;
    color: #8a8a8a;
    margin-right: 4px;
  }
  /* Graveyard cards are shown shrunk; they only matter as revive targets. */
  .gycard {
    transform: scale(0.6);
    margin: -18px -12px;
  }
  .gycard.targetable :global(.tile) {
    outline: 3px solid #ff6b6b;
    cursor: crosshair;
    border-radius: 8px;
  }
  .status {
    display: flex;
    align-items: center;
    gap: 14px;
    justify-content: center;
    padding: 6px;
    border-top: 1px solid #2c3c2c;
    border-bottom: 1px solid #2c3c2c;
  }
  .status .turn {
    color: #bbb;
  }
  .status .phase {
    font-weight: 800;
    color: #ffe08a;
    font-size: 16px;
  }
  .status .whose {
    color: #9fd9a9;
    font-size: 13px;
  }
  .next {
    margin-left: 8px;
  }
  .chainbar {
    text-align: center;
    font-size: 13px;
    color: #c9b3ff;
    background: rgba(107, 63, 160, 0.25);
    border-radius: 6px;
    padding: 4px;
  }
  .respond {
    border-color: #c9b3ff;
  }
  .respond-options {
    display: flex;
    flex-direction: column;
    gap: 8px;
    margin-top: 12px;
  }
  .passbtn {
    background: #555;
    color: #eee;
  }
  .banner {
    text-align: center;
    background: #3a2e12;
    color: #ffe08a;
    padding: 6px;
    border-radius: 6px;
    font-size: 13px;
  }
  .banner button {
    margin-left: 10px;
    padding: 2px 8px;
  }
  .hand {
    display: flex;
    gap: 6px;
    justify-content: center;
    flex-wrap: wrap;
    min-height: 120px;
    padding-top: 6px;
  }
  .handcard {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 3px;
  }
  .handcard.dim {
    opacity: 0.5;
  }
  .handcard [draggable='true'] {
    cursor: grab;
  }
  .setbtn {
    font-size: 10px;
    padding: 2px 8px;
  }
  .log {
    background: #0f0f0c;
    border: 1px solid #2c2c2c;
    border-radius: 10px;
    padding: 10px;
    display: flex;
    flex-direction: column;
    min-height: 0;
  }
  .log h2 {
    font-size: 14px;
    margin: 0 0 8px;
    color: #d9bf7a;
  }
  .loglines {
    overflow-y: auto;
    font-size: 12px;
    line-height: 1.5;
    flex: 1;
  }
  .logline {
    white-space: pre-wrap;
    color: #cfcfcf;
    border-bottom: 1px solid #1c1c18;
    padding: 1px 0;
  }
  .overlay {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.7);
    display: flex;
    align-items: center;
    justify-content: center;
  }
  .resultcard {
    background: #1c1c22;
    border: 2px solid #b8923a;
    border-radius: 12px;
    padding: 30px 50px;
    text-align: center;
  }
  .resultcard.win {
    border-color: #6cff9e;
  }
  .resultcard h2 {
    margin: 0 0 8px;
    font-size: 28px;
  }
</style>
