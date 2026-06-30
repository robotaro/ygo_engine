<script>
  import { onMount } from 'svelte'
  import { fly, fade } from 'svelte/transition'
  import { flip } from 'svelte/animate'
  import { tweened } from 'svelte/motion'
  import { cubicOut } from 'svelte/easing'
  import CardTile from './lib/CardTile.svelte'
  import Launcher from './lib/Launcher.svelte'
  import {
    board,
    legal,
    responsePrompt,
    targetRequest,
    choosePrompt,
    ritualPrompt,
    awaiting,
    logs,
    result,
    connected,
    online,
    profile,
    tournamentOutcome,
    startHealthMonitor,
    leaveGame,
    startTournamentDuel,
    sendIntent,
  } from './lib/store.js'

  onMount(startHealthMonitor)

  let draggedIid = null
  let selectedAttacker = null
  let pendingTribute = null // {iid, zoneIndex, needed, chosen[], mode}
  let pendingTarget = null // {iid, zoneIndex, candidates[], needed, chosen[]}
  let targetChosen = [] // accumulating clicks for an engine-driven target prompt
  let openGy = null // which Graveyard's contents are expanded ('you' | 'opp')
  let ritualChosen = [] // iids picked for a Ritual Tribute
  let unionSource = null // a Union monster picked, awaiting a host to equip to
  let preview = null // a card shown enlarged for reading (left-click)
  let previewCtx = null // { where, zoneIndex } so the modal can offer that card's actions
  let ctx = null // right-click context menu: { x, y, items[] }

  // The Launcher (deck picker / builder) shows until a duel starts.

  // reactive views
  $: you = $board?.you
  $: opp = $board?.opponent
  $: phase = $board?.phase
  $: phaseIndex = PHASES.findIndex((p) => p.key === phase)

  // Life points count up/down instead of snapping, and flash red on damage.
  const youLp = tweened(8000, { duration: 550, easing: cubicOut })
  const oppLp = tweened(8000, { duration: 550, easing: cubicOut })
  $: if (you) youLp.set(you.lifePoints)
  $: if (opp) oppLp.set(opp.lifePoints)
  let youHit = false
  let oppHit = false
  onMount(() => {
    let py = null
    let po = null
    return board.subscribe((b) => {
      if (!b) {
        py = po = null
        return
      }
      if (py != null && b.you.lifePoints < py) {
        youHit = true
        setTimeout(() => (youHit = false), 600)
      }
      if (po != null && b.opponent.lifePoints < po) {
        oppHit = true
        setTimeout(() => (oppHit = false), 600)
      }
      py = b.you.lifePoints
      po = b.opponent.lifePoints
    })
  })
  $: yourTurn = $awaiting
  $: dragging = draggedIid != null
  $: draggingMonster = draggedIid != null && !!summonOptions(draggedIid)
  $: draggingSpellTrap = draggedIid != null && (canActivate(draggedIid) || canSet(draggedIid))
  $: draggingFieldSpell = draggedIid != null && isFieldSpell(draggedIid) && canActivate(draggedIid)
  $: if (phase !== 'battle_phase') selectedAttacker = null
  // Union: hosts the picked Union may equip to (highlighted while choosing).
  $: unionHosts = unionSource != null && $legal ? ($legal.unionEquippable?.[unionSource] ?? []) : []
  $: if (!$legal) unionSource = null
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
  // A Graveyard is "live" (auto-expanded) when one of its cards is a valid target.
  $: youGyTargetable = !!you?.graveyard?.some((g) => targetCandidates.includes(g.iid))
  $: oppGyTargetable = !!opp?.graveyard?.some((g) => targetCandidates.includes(g.iid))

  // The turn's phase state machine, in order — rendered as a stepper.
  const PHASES = [
    { key: 'draw_phase', label: 'Draw' },
    { key: 'standby_phase', label: 'Standby' },
    { key: 'main_phase_1', label: 'Main 1' },
    { key: 'battle_phase', label: 'Battle' },
    { key: 'main_phase_2', label: 'Main 2' },
    { key: 'end_phase', label: 'End' },
  ]
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
  function canGeminiSummon(iid) {
    return $legal?.geminiSummonable?.includes(iid)
  }
  function canSpecialSummon(iid) {
    return $legal?.specialSummonable?.includes(iid)
  }
  function specialSummon(iid) {
    if (canSpecialSummon(iid)) sendIntent({ kind: 'specialSummon', iid })
  }
  function canUnionEquip(iid) {
    return !!$legal?.unionEquippable?.[iid]?.length
  }
  function canUnionUnequip(iid) {
    return $legal?.unionUnequippable?.includes(iid)
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

  // --- card preview: left-click any known card to enlarge and read it ---
  function findCard(iid) {
    const pools = [
      you?.hand,
      you?.monsterZones,
      you?.spellTrapZones,
      you?.graveyard,
      you?.fieldZone && [you.fieldZone],
      opp?.monsterZones,
      opp?.spellTrapZones,
      opp?.graveyard,
      opp?.fieldZone && [opp.fieldZone],
    ]
    for (const p of pools) {
      const c = p?.find?.((x) => x && x.iid === iid)
      if (c) return c
    }
    return null
  }
  function enlarge(card, where = null, zoneIndex = null) {
    if (card && card.name != null) {
      preview = card
      previewCtx = { where, zoneIndex }
      ctx = null
    }
  }
  function closeOverlays() {
    preview = null
    previewCtx = null
    ctx = null
  }

  // --- right-click context menu: a card's legal actions live here, so a plain
  //     click never changes a monster's battle position by accident ---
  function summonToFirstZone(iid) {
    if (!yourTurn) return
    const opts = summonOptions(iid)
    if (!opts || !opts.summon?.length) return
    const zoneIndex = firstEmptyZone()
    if (zoneIndex == null) return
    if (opts.summon.some((c) => c.length === 0)) {
      sendIntent({ kind: 'summon', iid, tributes: [], zoneIndex })
    } else {
      pendingTribute = { iid, zoneIndex, needed: opts.summon[0].length, chosen: [], mode: 'summon' }
    }
  }
  // The gameplay actions available for a card in a given place — shared by the
  // right-click menu and the click-to-open card modal.
  function cardActions(card, where, zoneIndex) {
    const items = []
    const iid = card?.iid
    if (yourTurn && card && card.name != null) {
      if (where === 'ownMonster') {
        if (phase === 'battle_phase' && attackTargets(iid))
          items.push({ label: 'Declare Attack', fn: () => (selectedAttacker = iid) })
        if (canChangePos(iid))
          items.push({
            label: isDefense(card) ? 'Switch to Attack' : 'Switch to Defense',
            fn: () => sendIntent({ kind: 'changePosition', iid }),
          })
        if (canFlip(iid))
          items.push({ label: 'Flip Summon', fn: () => sendIntent({ kind: 'flip', iid }) })
        if (canGeminiSummon(iid))
          items.push({ label: 'Gemini Summon', fn: () => sendIntent({ kind: 'geminiSummon', iid }) })
        if (canUnionEquip(iid))
          items.push({ label: 'Equip as Union…', fn: () => (unionSource = iid) })
      } else if (where === 'ownSpellTrap') {
        if (canActivate(iid)) items.push({ label: 'Activate', fn: () => beginActivate(iid, zoneIndex) })
        if (canUnionUnequip(iid))
          items.push({ label: 'Unequip Union', fn: () => sendIntent({ kind: 'unionUnequip', union: iid }) })
      } else if (where === 'hand') {
        const opts = summonOptions(iid)
        if (opts?.summon?.length) items.push({ label: 'Summon', fn: () => summonToFirstZone(iid) })
        if (canSpecialSummon(iid)) items.push({ label: 'Special Summon', fn: () => specialSummon(iid) })
        if (canActivate(iid)) items.push({ label: 'Activate', fn: () => activateSpell(iid) })
        if (canSet(iid)) items.push({ label: 'Set', fn: () => setCard(iid) })
        else if (opts?.set?.length) items.push({ label: 'Set', fn: () => onSet(iid) })
      }
    }
    return items
  }
  function buildContext(card, where, zoneIndex) {
    const items = cardActions(card, where, zoneIndex)
    if (card && card.name != null)
      items.push({ label: 'Enlarge', fn: () => enlarge(card, where, zoneIndex) })
    return items
  }
  function openContext(e, card, where, zoneIndex) {
    const items = buildContext(card, where, zoneIndex)
    if (!items.length) return
    e.preventDefault()
    const w = 190
    const h = 12 + items.length * 32
    ctx = {
      x: Math.max(6, Math.min(e.clientX, window.innerWidth - w - 6)),
      y: Math.max(6, Math.min(e.clientY, window.innerHeight - h - 6)),
      items,
    }
  }
  function runCtx(item) {
    ctx = null
    item.fn()
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

  // engine-driven single-card chooser (e.g. which Fusion Monster to summon)
  function chooseCard(iid) {
    sendIntent({ kind: 'choose', iid })
  }

  // Ritual Tribute selection (multi-select with a Level total target)
  $: if (!$ritualPrompt) ritualChosen = []
  $: ritualTotal = $ritualPrompt
    ? ritualChosen.reduce(
        (n, iid) => n + ($ritualPrompt.options.find((o) => o.iid === iid)?.level ?? 0),
        0,
      )
    : 0
  $: ritualFieldPicked = $ritualPrompt
    ? ritualChosen.filter(
        (iid) => $ritualPrompt.options.find((o) => o.iid === iid)?.where === 'field',
      ).length
    : 0
  $: ritualValid =
    !!$ritualPrompt &&
    ritualTotal >= $ritualPrompt.required &&
    $ritualPrompt.freeZones + ritualFieldPicked >= 1
  function toggleTributePick(iid) {
    ritualChosen = ritualChosen.includes(iid)
      ? ritualChosen.filter((x) => x !== iid)
      : [...ritualChosen, iid]
  }
  function confirmTributes() {
    if (ritualValid) sendIntent({ kind: 'tributes', tributes: ritualChosen })
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

  // "up to N" target prompts: submit the current selection early (>= the minimum).
  function doneTargets() {
    const tr = $targetRequest
    if (!tr || !tr.upTo) return
    if (targetChosen.length < (tr.minCount ?? 1)) return
    sendIntent({ kind: 'target', targets: targetChosen })
    targetChosen = []
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
    if (!yourTurn) {
      enlarge(findCard(iid))
      return
    }
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
    // Union: a Union is picked, awaiting a host — click a highlighted host to equip.
    if (unionSource != null) {
      if (iid === unionSource) unionSource = null // click the Union again to cancel
      else if (unionHosts.includes(iid)) {
        sendIntent({ kind: 'unionEquip', union: unionSource, host: iid })
        unionSource = null
      }
      return
    }
    if (phase === 'battle_phase' && attackTargets(iid)) {
      selectedAttacker = selectedAttacker === iid ? null : iid
      return
    }
    // Idle click just reads the card. Position change / Flip / Gemini / Union
    // all live in the right-click menu now, so nothing happens by accident.
    enlarge(findCard(iid))
  }

  function onClickOppMonster(iid) {
    if (yourTurn && $targetRequest) return chooseEngineTarget(iid)
    if (yourTurn && pendingTarget) return chooseTarget(iid)
    if (
      yourTurn &&
      phase === 'battle_phase' &&
      selectedAttacker != null &&
      validTargets.includes(iid)
    ) {
      lunge(selectedAttacker, iid)
      sendIntent({ kind: 'attack', attacker: selectedAttacker, target: iid })
      selectedAttacker = null
      return
    }
    enlarge(findCard(iid))
  }

  function onDirectAttack() {
    if (!yourTurn || phase !== 'battle_phase' || selectedAttacker == null) return
    if (validTargets.includes(null)) {
      lunge(selectedAttacker, null)
      sendIntent({ kind: 'attack', attacker: selectedAttacker, target: null })
      selectedAttacker = null
    }
  }

  // The attacker lunges toward its target (a monster, or the opponent on a
  // direct attack) and recoils, while the engine resolves the battle.
  function lunge(attackerIid, targetIid) {
    if (window.matchMedia?.('(prefers-reduced-motion: reduce)').matches) return
    const aEl = document.querySelector(`.slot.mon.own[data-iid="${attackerIid}"]`)
    if (!aEl || !aEl.animate) return
    const tEl =
      targetIid != null
        ? document.querySelector(`.slot.mon[data-iid="${targetIid}"]`)
        : document.querySelector('.playerbar.opp')
    const a = aEl.getBoundingClientRect()
    let dx = 0
    let dy = -44
    if (tEl) {
      const t = tEl.getBoundingClientRect()
      dx = t.left + t.width / 2 - (a.left + a.width / 2)
      dy = t.top + t.height / 2 - (a.top + a.height / 2)
    }
    const k = 0.6 // charge most of the way, then snap back
    aEl.style.zIndex = '20'
    const anim = aEl.animate(
      [
        { transform: 'translate(0, 0)' },
        { transform: `translate(${dx * k}px, ${dy * k}px) scale(1.1)`, offset: 0.4 },
        { transform: 'translate(0, 0)' },
      ],
      { duration: 440, easing: 'cubic-bezier(.34, 1.15, .5, 1)' },
    )
    anim.onfinish = anim.oncancel = () => (aEl.style.zIndex = '')
  }

  // A Graveyard card may be a target (Monster Reborn picks either GY; Call of
  // the Haunted picks your own) for the active activation/forced-effect prompt.
  function onClickGraveyard(iid) {
    if (yourTurn && $targetRequest) return chooseEngineTarget(iid)
    if (yourTurn && pendingTarget) return chooseTarget(iid)
    enlarge(findCard(iid))
  }

  function toggleGy(side) {
    openGy = openGy === side ? null : side
  }

  // A Spell/Trap card may be a target (e.g. Mystical Space Typhoon hits either
  // player's), or — for your own Set Continuous Trap — something to activate.
  function onClickOwnSpellTrap(iid, zoneIndex) {
    if (yourTurn && $targetRequest) return chooseEngineTarget(iid)
    if (yourTurn && pendingTarget) return chooseTarget(iid)
    // Open the card modal; its action buttons (Activate, …) live there now.
    enlarge(findCard(iid), 'ownSpellTrap', zoneIndex)
  }

  function onClickOppSpellTrap(iid) {
    if (yourTurn && $targetRequest) return chooseEngineTarget(iid)
    if (yourTurn && pendingTarget) return chooseTarget(iid)
    enlarge(findCard(iid))
  }

  function isFieldSpell(iid) {
    const c = you?.hand.find((x) => x.iid === iid)
    return c?.subtype === 'Field'
  }

  // The Field Zone holds a Field Spell; it can also be a target (Mystical Space
  // Typhoon hits Field Spells too).
  function onClickFieldZone(slot) {
    if (!slot) return
    if (yourTurn && $targetRequest) return chooseEngineTarget(slot.iid)
    if (yourTurn && pendingTarget) return chooseTarget(slot.iid)
    enlarge(slot)
  }

  function onDropField(e) {
    e.preventDefault()
    if (!yourTurn || draggedIid == null) return
    const iid = draggedIid
    draggedIid = null
    if (isFieldSpell(iid) && canActivate(iid)) beginActivate(iid, null) // engine routes it to the Field Zone
  }

  function onHandClick(iid) {
    if (mustDiscard) return sendIntent({ kind: 'discard', iid })
    enlarge(findCard(iid))
  }

  function nextPhase() {
    selectedAttacker = null
    pendingTribute = null
    pendingTarget = null
    sendIntent({ kind: 'pass' })
  }

</script>

<main class:wide={!$board}>
  <header>
    <h1>ygo_engine</h1>
    <div class="conn" class:on={$connected || $online} class:live={$connected}>
      {$connected ? 'in duel' : $online ? 'online' : 'offline'}
    </div>
    {#if $profile}
      <div class="dp" title="Duelist Points — earned from duels, spent on packs">
        ◈ {$profile.duelistPoints.toLocaleString()} DP
      </div>
    {/if}
    {#if $board}
      <button class="menubtn" onclick={leaveGame}>⏎ Menu</button>
    {/if}
  </header>

  {#if !$board}
    <Launcher />
  {:else}
    <div class="table">
      <!-- Opponent -->
      <div
        class="playerbar opp"
        class:targetable={selectedAttacker != null && validTargets.includes(null)}
        onclick={onDirectAttack}
      >
        <div class="who">{opp.name}</div>
        <div class="lp" class:hit={oppHit}>LP {Math.round($oppLp)}</div>
        <div class="piles">hand {opp.handCount}</div>
        <div class="ohand">
          {#each Array(opp.handCount) as _}<div class="minicard back"></div>{/each}
        </div>
      </div>

      <!-- Opponent's half — their mat rotated 180° (Spell/Trap line on top). -->
      <div class="mat opp">
        <!-- back line: Deck · Spell & Trap · Extra Deck -->
        <div class="slot pile deck">
          {#if opp.deckCount}<div class="pileback"></div>
            <span class="count">{opp.deckCount}</span>{/if}
          <span class="zlabel">Deck</span>
        </div>
        {#each opp.spellTrapZones as slot}
          <div
            class="slot st"
            class:targetable={slot && targetCandidates.includes(slot.iid)}
            onclick={() => slot && onClickOppSpellTrap(slot.iid)}
            oncontextmenu={(e) => slot && openContext(e, slot, 'opp')}
          >
            <CardTile card={slot} faceDown={slot?.faceDown} small />
          </div>
        {/each}
        <div class="slot pile extra">
          {#if opp.extraCount}<div class="pileback"></div>
            <span class="count">{opp.extraCount}</span>{/if}
          <span class="zlabel">Extra</span>
        </div>
        <!-- front line: Graveyard · Monsters · Field -->
        <div class="slot pile gy" class:targetable={oppGyTargetable} onclick={() => toggleGy('opp')}>
          {#if opp.graveyard.length}
            <CardTile card={opp.graveyard[opp.graveyard.length - 1]} faceDown small />
            <span class="count">{opp.graveyard.length}</span>
          {:else}
            <span class="zlabel">GY</span>
          {/if}
          {#if openGy === 'opp' || oppGyTargetable}
            <div class="gyflyout down" transition:fade={{ duration: 130 }}>
              {#each opp.graveyard as gy}
                <div
                  class="gycard"
                  class:targetable={targetCandidates.includes(gy.iid)}
                  onclick={(e) => {
                    e.stopPropagation()
                    onClickGraveyard(gy.iid)
                  }}
                  oncontextmenu={(e) => {
                    e.stopPropagation()
                    openContext(e, gy, 'gy')
                  }}
                >
                  <CardTile card={gy} small />
                </div>
              {/each}
            </div>
          {/if}
        </div>
        {#each opp.monsterZones as slot}
          <div
            class="slot mon"
            data-iid={slot?.iid}
            class:targetable={slot &&
              ((selectedAttacker != null && validTargets.includes(slot.iid)) ||
                targetCandidates.includes(slot.iid))}
            onclick={() => slot && onClickOppMonster(slot.iid)}
            oncontextmenu={(e) => slot && openContext(e, slot, 'opp')}
          >
            <CardTile card={slot} faceDown={slot?.faceDown} defense={isDefense(slot)} small />
          </div>
        {/each}
        <div
          class="slot field"
          class:targetable={opp.fieldZone && targetCandidates.includes(opp.fieldZone.iid)}
          onclick={() => onClickFieldZone(opp.fieldZone)}
          oncontextmenu={(e) => opp.fieldZone && openContext(e, opp.fieldZone, 'opp')}
        >
          <CardTile card={opp.fieldZone} small />
        </div>
      </div>

      <!-- Center status: the turn's phase state machine -->
      <div class="status">
        <span class="turn">Turn {$board.turnCount}</span>
        <div class="phasetrack">
          {#each PHASES as p, i}
            {#if i > 0}<span class="sep" class:past={i <= phaseIndex}></span>{/if}
            <span class="ph" class:on={i === phaseIndex} class:done={i < phaseIndex}>
              <span class="dot"></span>{p.label}
            </span>
          {/each}
        </div>
        <div class="statusright">
          <span class="whose">{yourTurn ? 'Your move' : '… opponent'}</span>
          {#if yourTurn && $legal?.canPass}
            <button class="next" onclick={nextPhase}>{NEXT_LABEL[phase] ?? 'Continue ▶'}</button>
          {/if}
        </div>
      </div>

      {#if $board.chain?.length}
        <div class="chainbar">
          ⛓ Chain:
          {#each $board.chain as link, i}{i > 0 ? ' → ' : ' '}{link.name}{/each}
        </div>
      {/if}

      <!-- Your half — your mat (Monster line on top, nearest the centre). -->
      <div class="mat you">
        <!-- front line: Field · Monsters · Graveyard -->
        <div
          class="slot field"
          class:drop={!you.fieldZone}
          class:armed={draggingFieldSpell}
          class:targetable={you.fieldZone && targetCandidates.includes(you.fieldZone.iid)}
          ondragover={(e) => e.preventDefault()}
          ondrop={onDropField}
          onclick={() => onClickFieldZone(you.fieldZone)}
          oncontextmenu={(e) => you.fieldZone && openContext(e, you.fieldZone, 'field')}
        >
          <CardTile card={you.fieldZone} small />
        </div>
        {#each you.monsterZones as slot, i}
          {#if slot}
            <div
              class="slot mon own"
              data-iid={slot.iid}
              class:selected={selectedAttacker === slot.iid || unionSource === slot.iid}
              class:tribute={pendingTribute?.chosen.includes(slot.iid)}
              class:targetable={targetCandidates.includes(slot.iid) || unionHosts.includes(slot.iid)}
              class:actionable={yourTurn &&
                (attackTargets(slot.iid) ||
                  canFlip(slot.iid) ||
                  canGeminiSummon(slot.iid) ||
                  canUnionEquip(slot.iid) ||
                  unionHosts.includes(slot.iid) ||
                  canChangePos(slot.iid) ||
                  pendingTribute ||
                  pendingTarget ||
                  $targetRequest)}
              title={canGeminiSummon(slot.iid)
                ? 'Gemini Summon — unlock this monster’s effect'
                : canUnionEquip(slot.iid)
                  ? 'Union — click, then click a host to equip'
                  : null}
              onclick={() => onClickOwnMonster(slot.iid)}
              oncontextmenu={(e) => openContext(e, slot, 'ownMonster')}
            >
              <CardTile card={slot} faceDown={slot?.faceDown} peek={slot?.faceDown} defense={isDefense(slot)} small />
              {#if slot.geminiUnlocked}<span class="badge gemini">★</span>{/if}
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
        <div class="slot pile gy" class:targetable={youGyTargetable} onclick={() => toggleGy('you')}>
          {#if you.graveyard.length}
            <CardTile card={you.graveyard[you.graveyard.length - 1]} faceDown small />
            <span class="count">{you.graveyard.length}</span>
          {:else}
            <span class="zlabel">GY</span>
          {/if}
          {#if openGy === 'you' || youGyTargetable}
            <div class="gyflyout" transition:fade={{ duration: 130 }}>
              {#each you.graveyard as gy}
                <div
                  class="gycard"
                  class:targetable={targetCandidates.includes(gy.iid)}
                  onclick={(e) => {
                    e.stopPropagation()
                    onClickGraveyard(gy.iid)
                  }}
                  oncontextmenu={(e) => {
                    e.stopPropagation()
                    openContext(e, gy, 'gy')
                  }}
                >
                  <CardTile card={gy} small />
                </div>
              {/each}
            </div>
          {/if}
        </div>
        <!-- back line: Extra Deck · Spell & Trap · Deck -->
        <div class="slot pile extra">
          {#if you.extraCount}<div class="pileback"></div>
            <span class="count">{you.extraCount}</span>{/if}
          <span class="zlabel">Extra</span>
        </div>
        {#each you.spellTrapZones as slot, i}
          {#if slot}
            <div
              class="slot st"
              class:actionable={yourTurn && (canActivate(slot.iid) || canUnionUnequip(slot.iid))}
              class:targetable={targetCandidates.includes(slot.iid)}
              title={canUnionUnequip(slot.iid) ? 'Unequip this Union (Special Summon it back)' : null}
              onclick={() => onClickOwnSpellTrap(slot.iid, i)}
              oncontextmenu={(e) => openContext(e, slot, 'ownSpellTrap', i)}
            >
              <CardTile card={slot} faceDown={slot?.faceDown} peek={slot?.faceDown} small />
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
        <div class="slot pile deck">
          {#if you.deckCount}<div class="pileback"></div>
            <span class="count">{you.deckCount}</span>{/if}
          <span class="zlabel">Deck</span>
        </div>
      </div>

      <div class="playerbar you">
        <div class="who">{you.name}</div>
        <div class="lp" class:hit={youHit}>LP {Math.round($youLp)}</div>
      </div>

      <!-- Hand -->
      {#if $targetRequest}
        <div class="banner">
          <strong>{$targetRequest.source}</strong> — {$targetRequest.prompt}
          (click a highlighted monster · {targetChosen.length}/{$targetRequest.count})
          {#if $targetRequest.upTo}
            <button
              disabled={targetChosen.length < ($targetRequest.minCount ?? 1)}
              onclick={doneTargets}
            >
              Done ✓
            </button>
          {/if}
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
        {#each you.hand as card (card.iid)}
          {@const opts = summonOptions(card.iid)}
          {@const activatable = canActivate(card.iid)}
          {@const settable = canSet(card.iid)}
          {@const specialSummonable = canSpecialSummon(card.iid)}
          <div
            class="handcard"
            class:dim={yourTurn &&
              !opts &&
              !activatable &&
              !settable &&
              !specialSummonable &&
              !mustDiscard}
            animate:flip={{ duration: 240 }}
            in:fly={{ y: 26, duration: 220 }}
            out:fly={{ y: -34, duration: 200 }}
          >
            <div
              draggable={yourTurn && (!!opts || activatable || settable)}
              ondragstart={() => (draggedIid = card.iid)}
              ondragend={() => (draggedIid = null)}
              onclick={() => onHandClick(card.iid)}
              oncontextmenu={(e) => openContext(e, card, 'hand')}
            >
              <CardTile {card} />
            </div>
            {#if yourTurn && specialSummonable}
              <button class="setbtn" onclick={() => specialSummon(card.iid)}>Sp. Summon</button>
            {:else if yourTurn && activatable}
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

  {#if $ritualPrompt && $awaiting}
    <div class="overlay">
      <div class="resultcard choose">
        <h2>{$ritualPrompt.prompt}</h2>
        <p class="rtotal" class:ok={ritualValid}>
          selected Level {ritualTotal} / {$ritualPrompt.required}
        </p>
        <div class="choose-options">
          {#each $ritualPrompt.options as opt}
            <button
              class="tributepick"
              class:picked={ritualChosen.includes(opt.iid)}
              onclick={() => toggleTributePick(opt.iid)}
            >
              <span class="cn">{opt.name}</span>
              <span class="lv">Lv{opt.level} · {opt.where}</span>
            </button>
          {/each}
        </div>
        <button class="confirm" disabled={!ritualValid} onclick={confirmTributes}>
          Tribute &amp; Summon
        </button>
      </div>
    </div>
  {/if}

  {#if $choosePrompt && $awaiting}
    <div class="overlay">
      <div class="resultcard choose">
        <h2>{$choosePrompt.prompt}</h2>
        <div class="choose-options">
          {#each $choosePrompt.options as opt}
            <button class="choosecard" onclick={() => chooseCard(opt.iid)}>
              <CardTile card={opt} small />
              <span class="cn">{opt.name}</span>
            </button>
          {/each}
        </div>
      </div>
    </div>
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
      {#if $tournamentOutcome}
        {@const t = $tournamentOutcome}
        <div class="resultcard" class:win={t.champion || t.won}>
          {#if t.pending}
            <h2>{t.won ? 'Round Won!' : 'Defeated'}</h2>
            <p>Tallying the bracket…</p>
          {:else if t.champion}
            <h2>🏆 Champion!</h2>
            <p>You took the whole bracket — <b>+{t.reward.toLocaleString()} DP</b></p>
            <button onclick={leaveGame}>Back to Menu</button>
          {:else if t.eliminated}
            <h2>Eliminated</h2>
            <p>Knocked out after {t.wins} {t.wins === 1 ? 'win' : 'wins'}. {$result.reason}</p>
            <button onclick={leaveGame}>Back to Bracket</button>
          {:else if t.next}
            <h2>Round Won!</h2>
            <p>Next up: <b>{t.next.name}</b></p>
            <button class="btn-primary" onclick={() => startTournamentDuel(undefined, t.deck, t.next.id)}>
              Play Next Round ▶
            </button>
            <button onclick={leaveGame}>Back to Bracket</button>
          {:else}
            <h2>{t.won ? 'Round Won!' : 'Defeated'}</h2>
            <p>{$result.reason}</p>
            <button onclick={leaveGame}>Back to Bracket</button>
          {/if}
        </div>
      {:else}
        <div class="resultcard" class:win={$result.youWin}>
          <h2>{$result.youWin ? 'You Win!' : $result.winner == null ? 'Draw' : 'You Lose'}</h2>
          <p>{$result.reason}</p>
          <button onclick={leaveGame}>Back to Menu</button>
        </div>
      {/if}
    </div>
  {/if}
</main>

<svelte:window
  onkeydown={(e) => {
    if (e.key === 'Escape') closeOverlays()
  }}
/>

{#if ctx}
  <button
    class="ctxbackdrop"
    aria-label="Close menu"
    onclick={() => (ctx = null)}
    oncontextmenu={(e) => {
      e.preventDefault()
      ctx = null
    }}
  ></button>
  <div class="ctxmenu" style="left:{ctx.x}px; top:{ctx.y}px">
    {#each ctx.items as item}
      <button onclick={() => runCtx(item)}>{item.label}</button>
    {/each}
  </div>
{/if}

{#if preview}
  {@const actions = cardActions(preview, previewCtx?.where, previewCtx?.zoneIndex)}
  <div class="cardzoom" role="presentation" onclick={closeOverlays} transition:fade={{ duration: 120 }}>
    <div class="zoombody" role="dialog" tabindex="-1" onclick={(e) => e.stopPropagation()}>
      <button class="zoomx" aria-label="Close" onclick={closeOverlays}>✕</button>
      <div class="zoomart">
        <div class="zoomfallback">{preview.name}</div>
        {#if preview.imageId}
          <img
            src={`/cards/${preview.imageId}.jpg`}
            alt={preview.name}
            onerror={(e) => e.currentTarget.remove()}
          />
        {/if}
      </div>
      <div class="zoominfo">
        <h3>{preview.name}</h3>
        <div class="zoommeta">
          {#if preview.cardType === 'monster'}
            {#if preview.attribute}<span>{preview.attribute}</span>{/if}
            {#if preview.level != null}<span>Level {preview.level}</span>{/if}
            <span>ATK {preview.attack ?? '?'} · DEF {preview.defense ?? '?'}</span>
          {:else}
            <span>{preview.cardType}{preview.subtype ? ` · ${preview.subtype}` : ''}</span>
          {/if}
        </div>
        {#if preview.text}<p class="zoomtext">{preview.text}</p>{/if}
        {#if actions.length}
          <div class="zoomactions">
            {#each actions as a}
              <button
                class="zoomaction"
                onclick={() => {
                  a.fn()
                  closeOverlays()
                }}>{a.label}</button
              >
            {/each}
          </div>
        {/if}
      </div>
    </div>
  </div>
{/if}

<style>
  :global(body) {
    margin: 0;
    background: var(--bg);
    color: var(--text);
  }
  /* Single centered column so the battlefield sits in the middle of the screen;
     the duel log stacks below it. */
  main {
    display: flex;
    flex-direction: column;
    gap: 12px;
    max-width: 940px;
    margin: 0 auto;
    padding: 12px;
  }
  /* The menus (deck builder etc.) want room for a 5-wide card grid; the duel
     table stays at the narrower 940px. */
  main.wide {
    max-width: 1280px;
  }
  header {
    display: flex;
    align-items: center;
    gap: 12px;
  }
  h1 {
    font-size: 20px;
    margin: 0;
    color: var(--accent);
    letter-spacing: 0.01em;
  }
  .conn {
    font-size: 11px;
    padding: 2px 9px;
    border-radius: var(--r-pill);
    background: var(--danger-dim);
    color: var(--danger);
  }
  .conn.on {
    background: var(--success-dim);
    color: var(--success);
  }
  .conn.live {
    background: var(--accent);
    color: var(--accent-ink);
  }
  .dp {
    margin-left: auto;
    font-size: 13px;
    font-weight: 700;
    padding: 3px 11px;
    border-radius: var(--r-pill);
    background: var(--surface-2);
    color: var(--accent);
    border: 1px solid var(--line);
  }
  .menubtn {
    margin-left: 8px;
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
    transition: color 0.25s ease;
    transform-origin: left center;
  }
  .lp.hit {
    color: #ff5a5a;
    animation: lp-hit 0.5s ease;
  }
  @keyframes lp-hit {
    0% {
      transform: scale(1);
    }
    30% {
      transform: scale(1.22);
    }
    100% {
      transform: scale(1);
    }
  }
  @media (prefers-reduced-motion: reduce) {
    .lp.hit {
      animation: none;
    }
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
  /* Each player's half is the canonical 7-column mat:
     [Field | Monster x5 | Graveyard] over [Extra | Spell/Trap x5 | Deck]. */
  .mat {
    display: grid;
    grid-template-columns: repeat(7, 64px);
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
  .slot.mon {
    position: relative;
  }
  .badge.gemini {
    position: absolute;
    top: 1px;
    right: 2px;
    font-size: 12px;
    line-height: 1;
    color: #ffd76a;
    text-shadow: 0 0 3px #000, 0 0 3px #000;
    pointer-events: none;
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
  .slot.field {
    border: 1px solid #4a3f6a;
  }
  .slot.field.armed {
    outline: 2px dashed #c9b3ff;
    background: rgba(201, 179, 255, 0.08);
  }
  /* Corner piles: Deck, Extra Deck, Graveyard. */
  .slot.pile {
    position: relative;
    border: 1px solid #2f2f38;
    background: rgba(0, 0, 0, 0.18);
  }
  .slot.pile.gy {
    cursor: pointer;
  }
  .pileback {
    width: 64px;
    height: 90px;
    box-sizing: border-box;
    border-radius: 7px;
    border: 2px solid #7a5c1e;
    background: repeating-linear-gradient(45deg, #4a3a14, #4a3a14 6px, #5a4a1e 6px, #5a4a1e 12px);
  }
  .slot.pile .count {
    position: absolute;
    top: 2px;
    right: 2px;
    z-index: 2;
    background: rgba(0, 0, 0, 0.8);
    color: #ffe08a;
    font-size: 10px;
    font-weight: 800;
    border-radius: 3px;
    padding: 0 4px;
  }
  .zlabel {
    position: absolute;
    bottom: 3px;
    left: 0;
    right: 0;
    text-align: center;
    font-size: 8px;
    text-transform: uppercase;
    letter-spacing: 1px;
    color: #b9b9b9;
    text-shadow: 0 1px 2px #000;
    pointer-events: none;
  }
  /* The Graveyard pile expands its contents as a flyout (for revive targets). */
  .gyflyout {
    position: absolute;
    bottom: 96px;
    left: 50%;
    transform: translateX(-50%);
    z-index: 30;
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
    max-width: 360px;
    padding: 6px;
    background: #0f0f0c;
    border: 1px solid #3a3a30;
    border-radius: 8px;
    box-shadow: 0 6px 20px rgba(0, 0, 0, 0.6);
  }
  .gyflyout.down {
    bottom: auto;
    top: 96px;
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
    padding: 8px 4px;
    border-top: 1px solid var(--line);
    border-bottom: 1px solid var(--line);
  }
  .status .turn {
    color: var(--muted);
    font-size: 13px;
    font-weight: 600;
    flex: none;
    width: 110px;
  }
  .phasetrack {
    display: flex;
    align-items: center;
    justify-content: center;
    flex: 1;
  }
  .ph {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 12px;
    color: var(--faint);
    white-space: nowrap;
  }
  .ph .dot {
    width: 9px;
    height: 9px;
    border-radius: 50%;
    background: var(--line-strong);
    transition: all 0.15s ease;
  }
  .ph.done {
    color: var(--muted);
  }
  .ph.done .dot {
    background: var(--muted);
  }
  .ph.on {
    color: var(--text);
    font-weight: 700;
  }
  .ph.on .dot {
    background: var(--accent);
    box-shadow: 0 0 0 4px var(--warn-dim);
  }
  .sep {
    width: 22px;
    height: 2px;
    background: var(--line);
    margin: 0 6px;
    border-radius: var(--r-pill);
  }
  .sep.past {
    background: var(--muted);
  }
  .statusright {
    display: flex;
    align-items: center;
    justify-content: flex-end;
    gap: 10px;
    flex: none;
    width: 190px;
  }
  .whose {
    color: var(--muted);
    font-size: 12px;
  }
  .next {
    background: var(--accent);
    color: var(--accent-ink);
    border: none;
    font-weight: 700;
  }
  .next:hover {
    background: var(--accent-hover);
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
  .choose {
    border-color: #6cff9e;
  }
  .choose-options {
    display: flex;
    gap: 12px;
    margin-top: 14px;
    flex-wrap: wrap;
    justify-content: center;
  }
  .choosecard {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 6px;
    background: transparent;
    padding: 6px;
    border-radius: 8px;
  }
  .choosecard:hover {
    background: rgba(108, 255, 158, 0.12);
  }
  .choosecard .cn {
    font-size: 11px;
    color: #eee;
    max-width: 80px;
  }
  .rtotal {
    color: #ff8a7a;
    font-weight: 700;
    margin: 4px 0 0;
  }
  .rtotal.ok {
    color: #7dff9e;
  }
  .tributepick {
    display: flex;
    flex-direction: column;
    gap: 2px;
    background: #2b2b33;
    color: #eee;
    border: 2px solid #444;
    padding: 8px 10px;
    border-radius: 7px;
  }
  .tributepick .lv {
    font-size: 10px;
    color: #bbb;
  }
  .tributepick.picked {
    border-color: #6cff9e;
    background: rgba(108, 255, 158, 0.15);
  }
  .confirm {
    margin-top: 14px;
  }
  .confirm:disabled {
    opacity: 0.4;
    cursor: not-allowed;
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
    background: var(--surface);
    border: 1px solid var(--line);
    border-radius: var(--r-lg);
    padding: 10px;
    display: flex;
    flex-direction: column;
    min-height: 0;
  }
  .log h2 {
    font-size: 14px;
    margin: 0 0 8px;
    color: var(--muted);
  }
  .loglines {
    overflow-y: auto;
    font-size: 12px;
    line-height: 1.5;
    max-height: 160px;
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

  /* Card preview (left-click any card to read it big). */
  .cardzoom {
    position: fixed;
    inset: 0;
    z-index: 200;
    background: rgba(0, 0, 0, 0.74);
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 24px;
  }
  .zoombody {
    position: relative;
    display: flex;
    gap: 20px;
    background: var(--surface);
    border: 1px solid var(--line);
    border-radius: var(--r-lg);
    padding: 18px;
    max-width: 620px;
    box-shadow: 0 20px 60px rgba(0, 0, 0, 0.6);
  }
  .zoomx {
    position: absolute;
    top: 10px;
    right: 10px;
    width: 30px;
    height: 30px;
    padding: 0;
    font-size: 14px;
    line-height: 1;
    border-radius: var(--r);
    background: var(--surface-2);
    color: var(--muted);
    border: 1px solid var(--line);
  }
  .zoomx:hover {
    background: var(--surface-3);
    color: var(--text);
  }
  .zoomart {
    position: relative;
    width: 232px;
    height: 338px;
    flex: none;
    border-radius: var(--r);
    overflow: hidden;
    border: 1px solid var(--line-strong);
    background: var(--surface-2);
    display: flex;
    align-items: center;
    justify-content: center;
  }
  .zoomart img {
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
    object-fit: cover;
  }
  .zoomfallback {
    font-size: 16px;
    font-weight: 700;
    color: var(--text);
    text-align: center;
    padding: 12px;
  }
  .zoominfo {
    display: flex;
    flex-direction: column;
    max-width: 300px;
    padding-right: 26px;
  }
  .zoominfo h3 {
    margin: 2px 0 8px;
    font-size: 20px;
    color: var(--accent);
  }
  .zoommeta {
    font-size: 12px;
    color: var(--muted);
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin-bottom: 10px;
  }
  .zoomtext {
    font-size: 13px;
    line-height: 1.5;
    color: var(--text);
    overflow-y: auto;
    flex: 1;
    white-space: pre-wrap;
    margin: 0;
  }
  .zoomactions {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin-top: 14px;
  }
  .zoomaction {
    background: var(--accent);
    color: var(--accent-ink);
    border: none;
    font-weight: 700;
  }
  .zoomaction:hover {
    background: var(--accent-hover);
  }

  /* Right-click context menu. */
  .ctxbackdrop {
    position: fixed;
    inset: 0;
    z-index: 210;
    background: none;
    border: none;
    padding: 0;
    cursor: default;
  }
  .ctxmenu {
    position: fixed;
    z-index: 211;
    background: #1b1b24;
    border: 1px solid #44444f;
    border-radius: 8px;
    padding: 4px;
    min-width: 168px;
    box-shadow: 0 12px 30px rgba(0, 0, 0, 0.6);
    display: flex;
    flex-direction: column;
  }
  .ctxmenu button {
    text-align: left;
    background: none;
    border: none;
    color: #eaeaf0;
    padding: 7px 10px;
    border-radius: 5px;
    font-size: 13px;
    cursor: pointer;
  }
  .ctxmenu button:hover {
    background: #2e2e3c;
  }
  @media (prefers-reduced-motion: reduce) {
    .cardzoom {
      transition: none;
    }
  }
</style>
