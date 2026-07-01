<script>
  import { onMount } from 'svelte'
  import { fly, fade } from 'svelte/transition'
  import { flip } from 'svelte/animate'
  import { tweened } from 'svelte/motion'
  import { cubicOut } from 'svelte/easing'
  import CardTile from './lib/CardTile.svelte'
  import Launcher from './lib/Launcher.svelte'
  import RewardPicker from './lib/RewardPicker.svelte'
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
    battleFx,
    startHealthMonitor,
    leaveGame,
    startTournamentDuel,
    sendIntent,
  } from './lib/store.js'

  onMount(startHealthMonitor)

  // Floating "-1200" damage numbers spawned during combat (see playBattleFx).
  let damageFloaters = []
  let floaterSeq = 0

  // Win-reward pack pick: show it once per result, until the player claims it.
  let rewardClaimed = false
  $: if ($result) rewardClaimed = false

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
  let placing = null // { iid, action, zoneType } while picking a zone to play a card into
  let dropChoice = null // { iid, zoneIndex, x, y } — "Summon or Set?" after a drop
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
  $: placingMonster = placing?.zoneType === 'monster'
  $: placingSpellTrap = placing?.zoneType === 'spellTrap'
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
  function closePreview() {
    preview = null
    previewCtx = null
    ctx = null
  }
  function closeOverlays() {
    closePreview()
    placing = null // Escape / backdrop cancels an in-progress placement too
    dropChoice = null
  }

  // Click-to-place: pick a zone (highlighted) to play a card into, instead of
  // auto-dropping it in the first free slot. Started from the card-read modal /
  // right-click menu; finished by clicking a highlighted zone (placeInZone).
  function beginPlace(iid, action) {
    // action: 'summon' | 'setMonster' (-> monster zones) | 'set' | 'activate' (-> spell/trap zones)
    preview = null
    previewCtx = null
    ctx = null
    const zoneType = action === 'summon' || action === 'setMonster' ? 'monster' : 'spellTrap'
    const hasRoom = zoneType === 'monster' ? firstEmptyZone() != null : firstEmptySpellZone() != null
    if (!hasRoom) return // board full — nothing to highlight
    placing = { iid, action, zoneType }
  }
  function placeInZone(zoneIndex) {
    const p = placing
    placing = null
    if (!p) return
    if (p.zoneType === 'monster') {
      playMonster(p.iid, zoneIndex, p.action)
    } else if (p.action === 'activate') {
      beginActivate(p.iid, zoneIndex)
    } else {
      sendIntent({ kind: 'set', iid: p.iid, zoneIndex }) // Spell/Trap Set face-down
    }
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
          items.push({ icon: '⚔️', label: 'Declare Attack', fn: () => (selectedAttacker = iid) })
        if (canChangePos(iid))
          items.push({
            icon: isDefense(card) ? '🗡️' : '🛡️',
            label: isDefense(card) ? 'Switch to Attack' : 'Switch to Defense',
            fn: () => sendIntent({ kind: 'changePosition', iid }),
          })
        if (canFlip(iid))
          items.push({ icon: '🔄', label: 'Flip Summon', fn: () => sendIntent({ kind: 'flip', iid }) })
        if (canGeminiSummon(iid))
          items.push({ icon: '🌟', label: 'Gemini Summon', fn: () => sendIntent({ kind: 'geminiSummon', iid }) })
        if (canUnionEquip(iid))
          items.push({ icon: '🔗', label: 'Equip as Union…', fn: () => (unionSource = iid) })
      } else if (where === 'ownSpellTrap') {
        if (canActivate(iid)) items.push({ icon: '⚡', label: 'Activate', fn: () => beginActivate(iid, zoneIndex) })
        if (canUnionUnequip(iid))
          items.push({ icon: '🔗', label: 'Unequip Union', fn: () => sendIntent({ kind: 'unionUnequip', union: iid }) })
      } else if (where === 'hand') {
        const opts = summonOptions(iid)
        if (opts?.summon?.length) items.push({ icon: '⚔️', label: 'Summon', fn: () => beginPlace(iid, 'summon') })
        if (canSpecialSummon(iid)) items.push({ icon: '✨', label: 'Special Summon', fn: () => specialSummon(iid) })
        if (canActivate(iid)) items.push({ icon: '⚡', label: 'Activate', fn: () => activateSpell(iid) })
        if (canSet(iid)) items.push({ icon: '🔽', label: 'Set', fn: () => beginPlace(iid, 'set') })
        else if (opts?.set?.length) items.push({ icon: '🛡️', label: 'Set', fn: () => beginPlace(iid, 'setMonster') })
      }
    }
    return items
  }
  function buildContext(card, where, zoneIndex) {
    const items = cardActions(card, where, zoneIndex)
    if (card && card.name != null)
      items.push({ icon: '🔍', label: 'Enlarge', fn: () => enlarge(card, where, zoneIndex) })
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
  // The ways a hand monster can be played (face-up Summon / face-down Set).
  function monsterPlays(iid) {
    const opts = summonOptions(iid)
    const plays = []
    if (opts?.summon?.length) plays.push('summon')
    if (opts?.set?.length) plays.push('setMonster')
    return plays
  }
  // Commit a monster to a zone (handling Tributes for high-Level monsters).
  function playMonster(iid, zoneIndex, action) {
    const opts = summonOptions(iid)
    const list = action === 'summon' ? opts?.summon : opts?.set
    if (!list?.length) return
    const kind = action === 'summon' ? 'summon' : 'set'
    if (list.some((c) => c.length === 0)) {
      sendIntent({ kind, iid, tributes: [], zoneIndex })
    } else {
      pendingTribute = { iid, zoneIndex, needed: list[0].length, chosen: [], mode: kind }
    }
  }

  function onDropSummon(e, zoneIndex) {
    e.preventDefault()
    if (!yourTurn || draggedIid == null) return
    const iid = draggedIid
    draggedIid = null
    const plays = monsterPlays(iid)
    if (plays.length === 0) return
    if (plays.length === 1) return playMonster(iid, zoneIndex, plays[0])
    // Both face-up Summon and face-down Set are possible — ask which.
    dropChoice = {
      iid,
      zoneIndex,
      x: Math.max(6, Math.min(e.clientX, window.innerWidth - 182)),
      y: Math.max(6, Math.min(e.clientY, window.innerHeight - 96)),
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
      enlarge(findCard(iid), 'ownMonster')
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
    // Idle click just reads the card (the modal offers its actions). Position
    // change / Flip / Gemini / Union also live in the right-click menu.
    enlarge(findCard(iid), 'ownMonster')
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
      sendIntent({ kind: 'attack', attacker: selectedAttacker, target: iid })
      selectedAttacker = null
      return
    }
    enlarge(findCard(iid))
  }

  function onDirectAttack() {
    if (!yourTurn || phase !== 'battle_phase' || selectedAttacker == null) return
    if (validTargets.includes(null)) {
      sendIntent({ kind: 'attack', attacker: selectedAttacker, target: null })
      selectedAttacker = null
    }
  }

  // ----- Combat animation. Driven by the server's "fx" event so it plays for
  // BOTH players' attacks (the bump used to fire on your click only). The event
  // arrives, we bump + flash + float the damage, then ~0.7s later the resolved
  // board lands and the dead monster dissolves away (the `dissolve` transition).
  const reduceMotion = () => window.matchMedia?.('(prefers-reduced-motion: reduce)').matches

  // The attacker charges its target (a monster, or the foe's bar on a direct
  // attack) and recoils. Works from either side of the field.
  function bump(attackerIid, targetIid) {
    const aEl = document.querySelector(`.slot.mon[data-iid="${attackerIid}"]`)
    if (!aEl || !aEl.animate) return
    const mine = !!aEl.closest('.mat.you')
    const tEl =
      targetIid != null
        ? document.querySelector(`.slot.mon[data-iid="${targetIid}"]`)
        : document.querySelector(mine ? '.playerbar.opp' : '.playerbar.you')
    const a = aEl.getBoundingClientRect()
    let dx = 0
    let dy = mine ? -44 : 44
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

  // A red flash + shake on the thing that got hit.
  function flashHit(el) {
    if (!el) return
    el.classList.remove('fxhit')
    void el.offsetWidth // restart the animation if it's already mid-flight
    el.classList.add('fxhit')
    setTimeout(() => el.classList.remove('fxhit'), 360)
  }

  // A "-1200" that rises and fades from a screen point.
  function floatDamage(amount, anchorEl) {
    if (!anchorEl || amount <= 0) return
    const r = anchorEl.getBoundingClientRect()
    const id = floaterSeq++
    damageFloaters = [...damageFloaters, { id, text: `-${amount}`, x: r.left + r.width / 2, y: r.top + r.height / 2 }]
    setTimeout(() => (damageFloaters = damageFloaters.filter((f) => f.id !== id)), 1000)
  }

  function playBattleFx(fx) {
    if (reduceMotion()) return
    bump(fx.attacker, fx.target)
    // Impact lands ~40% into the bump.
    setTimeout(() => {
      if (fx.target != null) flashHit(document.querySelector(`.slot.mon[data-iid="${fx.target}"]`))
      const dmg = fx.damage || {}
      if (dmg.opp > 0) floatDamage(dmg.opp, document.querySelector('.playerbar.opp'))
      if (dmg.you > 0) floatDamage(dmg.you, document.querySelector('.playerbar.you'))
    }, 175)
  }

  onMount(() => battleFx.subscribe((fx) => fx && playBattleFx(fx)))

  // A destroyed monster brightens, shrinks and sinks away (plays on its slot's
  // `out:` whenever a card leaves a monster zone — battle or effect).
  function dissolve(node, { duration = 600 }) {
    return {
      duration,
      easing: cubicOut,
      css: (t) => {
        const u = 1 - t // 0 at the start of the out, 1 at the end
        return `opacity:${t}; transform: scale(${0.5 + 0.5 * t}) translateY(${u * 12}px) rotate(${u * 8}deg); filter: brightness(${1 + u * 1.8}) blur(${u * 1.4}px);`
      },
    }
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
    enlarge(findCard(iid), 'hand')
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
            <span class="zlabel">Graveyard</span>
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
        {#each opp.monsterZones as slot, i (i)}
          <div
            class="slot mon"
            data-iid={slot?.iid}
            class:targetable={slot &&
              ((selectedAttacker != null && validTargets.includes(slot.iid)) ||
                targetCandidates.includes(slot.iid))}
            onclick={() => slot && onClickOppMonster(slot.iid)}
            oncontextmenu={(e) => slot && openContext(e, slot, 'opp')}
          >
            {#if slot}
              <div class="cardlayer" out:dissolve|local>
                <CardTile card={slot} faceDown={slot?.faceDown} defense={isDefense(slot)} small />
              </div>
            {:else}
              <CardTile card={null} small />
            {/if}
          </div>
        {/each}
        <div
          class="slot field"
          class:targetable={opp.fieldZone && targetCandidates.includes(opp.fieldZone.iid)}
          onclick={() => onClickFieldZone(opp.fieldZone)}
          oncontextmenu={(e) => opp.fieldZone && openContext(e, opp.fieldZone, 'opp')}
        >
          <CardTile card={opp.fieldZone} small />
          {#if !opp.fieldZone}<span class="zlabel">Field</span>{/if}
        </div>
      </div>

      <!-- Center status: the turn's phase state machine -->
      <div class="status">
        <span class="turn">Turn {$board.turnCount}</span>
        <div class="phasetrack">
          {#each PHASES as p, i}
            {#if i > 0}<span class="sep" class:past={i <= phaseIndex}></span>{/if}
            <span class="ph" class:on={i === phaseIndex} class:done={i < phaseIndex}>{p.label}</span>
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
          {#if !you.fieldZone}<span class="zlabel">Field</span>{/if}
        </div>
        {#each you.monsterZones as slot, i (i)}
          <!-- One persistent slot per zone, so a dying monster's dissolve (an
               absolute overlay) never adds a grid cell mid-transition. -->
          <div
            class="slot mon"
            class:own={!!slot}
            class:drop={!slot}
            class:armed={!slot && (draggingMonster || placingMonster)}
            data-iid={slot?.iid}
            class:selected={slot && (selectedAttacker === slot.iid || unionSource === slot.iid)}
            class:tribute={slot && pendingTribute?.chosen.includes(slot.iid)}
            class:targetable={slot &&
              (targetCandidates.includes(slot.iid) || unionHosts.includes(slot.iid))}
            class:actionable={slot &&
              yourTurn &&
              (attackTargets(slot.iid) ||
                canFlip(slot.iid) ||
                canGeminiSummon(slot.iid) ||
                canUnionEquip(slot.iid) ||
                unionHosts.includes(slot.iid) ||
                canChangePos(slot.iid) ||
                pendingTribute ||
                pendingTarget ||
                $targetRequest)}
            title={slot && canGeminiSummon(slot.iid)
              ? 'Gemini Summon — unlock this monster’s effect'
              : slot && canUnionEquip(slot.iid)
                ? 'Union — click, then click a host to equip'
                : null}
            onclick={() =>
              slot ? onClickOwnMonster(slot.iid) : placingMonster ? placeInZone(i) : null}
            oncontextmenu={(e) => slot && openContext(e, slot, 'ownMonster')}
            ondragover={(e) => !slot && e.preventDefault()}
            ondrop={(e) => !slot && onDropSummon(e, i)}
          >
            {#if slot}
              <div class="cardlayer" out:dissolve|local>
                <CardTile card={slot} faceDown={slot?.faceDown} peek={slot?.faceDown} defense={isDefense(slot)} small />
              </div>
              {#if slot.geminiUnlocked}<span class="badge gemini">★</span>{/if}
            {:else}
              <CardTile card={null} small />
            {/if}
          </div>
        {/each}
        <div class="slot pile gy" class:targetable={youGyTargetable} onclick={() => toggleGy('you')}>
          {#if you.graveyard.length}
            <CardTile card={you.graveyard[you.graveyard.length - 1]} faceDown small />
            <span class="count">{you.graveyard.length}</span>
          {:else}
            <span class="zlabel">Graveyard</span>
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
              class:armed={draggingSpellTrap || placingSpellTrap}
              onclick={() => placingSpellTrap && placeInZone(i)}
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
              <button class="setbtn" onclick={() => specialSummon(card.iid)}>✨ Sp. Summon</button>
            {:else if yourTurn && opts?.summon?.length}
              <button class="setbtn" onclick={() => beginPlace(card.iid, 'summon')}>⚔️ Summon</button>
            {:else if yourTurn && activatable}
              <button class="setbtn" onclick={() => activateSpell(card.iid)}>⚡ Activate</button>
            {:else if yourTurn && settable}
              <button class="setbtn" onclick={() => beginPlace(card.iid, 'set')}>🔽 Set</button>
            {:else if yourTurn && opts?.set?.length}
              <button class="setbtn" onclick={() => beginPlace(card.iid, 'setMonster')}>🛡️ Set</button>
            {/if}
          </div>
        {/each}
      </div>
    </div>

    <!-- Floating combat-damage numbers (fixed to the viewport). -->
    {#each damageFloaters as f (f.id)}
      <div class="dmgfloat" style="left:{f.x}px; top:{f.y}px">{f.text}</div>
    {/each}

    <aside class="log">
      <h2>Duel Log</h2>
      <div class="loglines">
        {#each $logs as line}<div class="logline">{line}</div>{/each}
      </div>
    </aside>

    {#if placing}
      <div class="placebar">
        <span>Choose a highlighted zone for <b>{findCard(placing.iid)?.name ?? 'this card'}</b></span>
        <button onclick={() => (placing = null)}>Cancel</button>
      </div>
    {/if}
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
      {#if $result.youWin && $result.pendingReward && !rewardClaimed}
        <div class="resultcard win">
          <RewardPicker onclaimed={() => (rewardClaimed = true)} />
        </div>
      {:else if $tournamentOutcome}
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
      <button onclick={() => runCtx(item)}>
        {#if item.icon}<span class="ctxicon">{item.icon}</span>{/if}{item.label}
      </button>
    {/each}
  </div>
{/if}

{#if dropChoice}
  <button
    class="ctxbackdrop"
    aria-label="Cancel"
    onclick={() => (dropChoice = null)}
    oncontextmenu={(e) => {
      e.preventDefault()
      dropChoice = null
    }}
  ></button>
  <div class="ctxmenu" style="left:{dropChoice.x}px; top:{dropChoice.y}px">
    <button
      onclick={() => {
        playMonster(dropChoice.iid, dropChoice.zoneIndex, 'summon')
        dropChoice = null
      }}><span class="ctxicon">⚔️</span>Summon (face-up)</button
    >
    <button
      onclick={() => {
        playMonster(dropChoice.iid, dropChoice.zoneIndex, 'setMonster')
        dropChoice = null
      }}><span class="ctxicon">🛡️</span>Set (face-down)</button
    >
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
                  closePreview() // keep `placing` if the action started a zone pick
                }}><span class="zoomicon">{a.icon}</span>{a.label}</button
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
    background:
      radial-gradient(130% 90% at 50% 0%, rgba(240, 180, 41, 0.05), transparent 55%),
      linear-gradient(180deg, var(--surface), var(--bg));
    border: 1px solid var(--line-strong);
    border-radius: var(--r-lg);
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
    border-radius: var(--r-sm);
    background: var(--surface);
    box-shadow: inset 0 0 0 1px var(--line);
  }
  .playerbar.targetable {
    outline: 2px solid var(--danger);
    cursor: crosshair;
  }
  .who {
    font-weight: 700;
  }
  .lp {
    font-size: 18px;
    font-weight: 800;
    color: var(--accent);
    transition: color 0.25s ease;
    transform-origin: left center;
  }
  .lp.hit {
    color: var(--danger);
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
    color: var(--muted);
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
    background: #5f3d2f;
    border: 1.5px solid #c6b78e;
    box-sizing: border-box;
  }
  /* Each player's half is the canonical 7-column mat:
     [Field | Monster x5 | Graveyard] over [Extra | Spell/Trap x5 | Deck]. */
  .mat {
    display: grid;
    grid-template-columns: repeat(7, 90px);
    gap: 8px;
    justify-content: center;
  }
  /* Square slots: wide enough that a card turned 90° for Defense fits without
     overlapping its neighbour. Cards stay portrait (64×90), centred in the well. */
  .slot {
    width: 90px;
    height: 90px;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: var(--r);
  }
  /* The 2×5 Monster/Spell play grid: raised, lit square wells you place cards
     into — visually distinct from the recessed corner piles. */
  .slot.mon,
  .slot.st {
    background: var(--surface-3);
    box-shadow: inset 0 0 0 1px var(--line);
  }
  .slot.drop.armed {
    outline: 2px dashed var(--success);
    background: var(--success-dim);
    cursor: pointer;
  }
  /* Banner shown while choosing a zone to place a card into. */
  .placebar {
    position: fixed;
    bottom: 18px;
    left: 50%;
    transform: translateX(-50%);
    display: flex;
    align-items: center;
    gap: 14px;
    background: var(--surface);
    border: 1px solid var(--success);
    color: var(--text);
    padding: 9px 16px;
    border-radius: var(--r-pill);
    z-index: 60;
    box-shadow: 0 6px 24px rgba(0, 0, 0, 0.5);
    font-size: 14px;
  }
  .placebar b {
    color: var(--success);
  }
  .placebar button {
    padding: 3px 12px;
    font-size: 12px;
  }
  .slot.mon.own.actionable {
    cursor: pointer;
  }
  .slot.mon.own.actionable:hover {
    outline: 2px solid var(--accent);
  }
  .slot.mon {
    position: relative;
  }
  /* The card sits in an absolute layer so its death `dissolve` overlays the slot
     (which keeps its grid cell) instead of collapsing the row. */
  .cardlayer {
    position: absolute;
    inset: 0;
    display: flex;
    align-items: center;
    justify-content: center;
  }
  /* Impact feedback on the monster that got hit: a red flash + a quick shake. */
  .slot.fxhit {
    animation: fxshake 0.34s ease;
  }
  .slot.fxhit::after {
    content: '';
    position: absolute;
    inset: -2px;
    border-radius: 8px;
    background: radial-gradient(circle, rgba(255, 70, 50, 0.85), rgba(255, 70, 50, 0) 70%);
    animation: fxflash 0.34s ease forwards;
    pointer-events: none;
    z-index: 6;
  }
  @keyframes fxshake {
    0%, 100% { transform: translate(0, 0); }
    20% { transform: translate(-3px, 2px); }
    45% { transform: translate(3px, -2px); }
    70% { transform: translate(-2px, 1px); }
  }
  @keyframes fxflash {
    from { opacity: 1; }
    to { opacity: 0; }
  }
  .dmgfloat {
    position: fixed;
    z-index: 60;
    transform: translate(-50%, -50%);
    font-size: 26px;
    font-weight: 900;
    color: #ff5a44;
    text-shadow: 0 0 6px rgba(0, 0, 0, 0.9), 0 2px 2px rgba(0, 0, 0, 0.9);
    pointer-events: none;
    animation: dmgrise 1s cubic-bezier(0.2, 0.7, 0.25, 1) forwards;
  }
  @keyframes dmgrise {
    0% { opacity: 0; transform: translate(-50%, -50%) scale(0.6); }
    18% { opacity: 1; transform: translate(-50%, -95%) scale(1.15); }
    100% { opacity: 0; transform: translate(-50%, -165%) scale(1); }
  }
  @media (prefers-reduced-motion: reduce) {
    .slot.fxhit, .slot.fxhit::after, .dmgfloat { animation: none; }
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
    outline: 2px solid var(--success);
  }
  .slot.tribute {
    outline: 2px solid #ff9e3d;
  }
  .slot.targetable {
    outline: 2px solid var(--danger);
    cursor: crosshair;
  }
  .slot.st.actionable {
    cursor: pointer;
  }
  .slot.st.actionable:hover {
    outline: 2px solid #c9b3ff;
  }
  /* The Field zone is a corner fixture (not part of the central 2×5), so it gets
     the dark recessed look — flagged with a distinct violet edge, not a grey well. */
  .slot.field {
    position: relative;
    background: rgba(0, 0, 0, 0.45);
    box-shadow: inset 0 0 0 1px #4a3f6a;
  }
  .slot.field.armed {
    outline: 2px dashed #c9b3ff;
    background: rgba(201, 179, 255, 0.1);
  }
  /* Corner piles: Deck, Extra Deck, Graveyard — recessed & darker than the play
     wells so they read as fixtures, never as a place you can drop a card. */
  .slot.pile {
    position: relative;
    box-shadow: inset 0 0 0 1px var(--line);
    background: rgba(0, 0, 0, 0.45);
  }
  .slot.pile.gy {
    cursor: pointer;
  }
  /* Deck / Extra stacks show the classic card back (brown + pastel frame + a
     dark central ellipse), matching CardTile's face-down back. */
  .pileback {
    position: relative;
    width: 64px;
    height: 90px;
    box-sizing: border-box;
    border-radius: var(--r);
    border: 4px solid #c6b78e;
    background: #5f3d2f;
  }
  .pileback::after {
    content: '';
    position: absolute;
    inset: 0;
    margin: auto;
    width: 55%;
    height: 64%;
    border-radius: 50%;
    background: #201f1e;
    box-shadow: inset 0 0 0 1px rgba(0, 0, 0, 0.45);
  }
  .slot.pile .count {
    position: absolute;
    top: 2px;
    right: 2px;
    z-index: 2;
    background: rgba(0, 0, 0, 0.8);
    color: var(--accent);
    font-size: 10px;
    font-weight: 800;
    border-radius: var(--r-sm);
    padding: 0 4px;
  }
  .zlabel {
    position: absolute;
    bottom: 4px;
    left: 50%;
    transform: translateX(-50%);
    font-size: 8px;
    text-transform: uppercase;
    letter-spacing: 1px;
    color: var(--muted);
    background: rgba(0, 0, 0, 0.62);
    padding: 1px 5px;
    border-radius: var(--r-sm);
    white-space: nowrap;
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
  /* Phase tracker: inactive phases are plain faint labels; the CURRENT phase is
     a bold amber capsule so it reads at a glance across the room. */
  .ph {
    font-size: 12px;
    color: var(--faint);
    white-space: nowrap;
    padding: 3px 8px;
    border-radius: var(--r-pill);
    transition: all 0.12s ease;
  }
  .ph.done {
    color: var(--muted);
  }
  .ph.on {
    background: var(--accent);
    color: var(--accent-ink);
    font-weight: 800;
    font-size: 13px;
    letter-spacing: 0.02em;
    padding: 4px 14px;
    box-shadow: 0 0 0 3px var(--warn-dim), 0 2px 8px rgba(0, 0, 0, 0.45);
  }
  .sep {
    width: 14px;
    height: 2px;
    background: var(--line);
    margin: 0 3px;
    border-radius: var(--r-pill);
  }
  .sep.past {
    background: var(--line-strong);
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
  .zoomicon {
    margin-right: 6px;
  }
  .ctxicon {
    display: inline-block;
    width: 1.3em;
    margin-right: 6px;
    text-align: center;
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
