<script>
  // One player's half of the board — the canonical 7-column mat. Rendered twice
  // by App.svelte (player="opp" then player="you"). The two halves are mirrored
  // in layout and differ in interactivity (your half drags/drops/tributes; the
  // opponent's is read/target-only), so each orientation has its own branch below.
  //
  // CRITICAL: the class names, `data-iid` attributes and DOM nesting here are what
  // the battle-FX code (lib/battleFx.js) locates by querySelector — `.mat.you`,
  // `.slot.mon[data-iid=…]`, and the runtime `.fxhit` class — so keep them in sync.
  import CardTile from './CardTile.svelte'
  import { cubicOut } from 'svelte/easing'
  import { isDefense } from './util.js'
  import { affordances, targetRequest } from './store.js'

  let {
    player, // 'you' | 'opp'
    p, // this player's board slice
    // reactive affordance/selection state, owned by App
    targetCandidates,
    gyTargetable,
    validTargets,
    selectedAttacker,
    unionSource,
    unionHosts,
    pendingTribute,
    pendingTarget,
    responseTargets,
    responseSources,
    yourTurn,
    phase,
    draggingFieldSpell,
    draggingMonster,
    draggingSpellTrap,
    placingMonster,
    placingSpellTrap,
    // callbacks
    openContext,
    toggleGy,
    onClickFieldZone,
    onClickOppSpellTrap,
    onClickOppMonster,
    onDropField,
    onClickOwnMonster,
    placeInZone,
    onDropSummon,
    onDropSpellTrap,
    onClickOwnSpellTrap,
  } = $props()

  // Per-iid affordance lookups read straight from the shared `$affordances`
  // store, so this component re-renders when the legal-moves payload changes.
  const attackTargets = (iid) => $affordances.attackTargets(iid)
  const canActivate = (iid) => $affordances.canActivate(iid)
  const canFlip = (iid) => $affordances.canFlip(iid)
  const canGeminiSummon = (iid) => $affordances.canGeminiSummon(iid)
  const canUnionEquip = (iid) => $affordances.canUnionEquip(iid)
  const canUnionUnequip = (iid) => $affordances.canUnionUnequip(iid)
  const canChangePos = (iid) => $affordances.canChangePos(iid)

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
</script>

{#if player === 'opp'}
  <!-- Opponent's half — their mat rotated 180° (Spell/Trap line on top). -->
  <div class="mat opp">
    <!-- back line: Deck · Spell & Trap · Extra Deck -->
    <div class="slot pile deck">
      {#if p.deckCount}<div class="pileback"></div>
        <span class="count">{p.deckCount}</span>{/if}
      <span class="zlabel">Deck</span>
    </div>
    {#each p.spellTrapZones as slot}
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
      {#if p.extraCount}<div class="pileback"></div>
        <span class="count">{p.extraCount}</span>{/if}
      <span class="zlabel">Extra</span>
    </div>
    <!-- front line: Graveyard · Monsters · Field -->
    <div class="slot pile gy" class:targetable={gyTargetable} onclick={() => toggleGy('opp')}>
      {#if p.graveyard.length}
        <CardTile card={p.graveyard[p.graveyard.length - 1]} faceDown small />
        <span class="count">{p.graveyard.length}</span>
      {/if}
      <span class="zlabel">Graveyard</span>
    </div>
    {#each p.monsterZones as slot, i (i)}
      <div
        class="slot mon"
        data-iid={slot?.iid}
        class:targetable={slot &&
          ((selectedAttacker != null && validTargets.includes(slot.iid)) ||
            targetCandidates.includes(slot.iid))}
        class:respondtarget={slot && responseTargets.has(slot.iid)}
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
      class:targetable={p.fieldZone && targetCandidates.includes(p.fieldZone.iid)}
      onclick={() => onClickFieldZone(p.fieldZone)}
      oncontextmenu={(e) => p.fieldZone && openContext(e, p.fieldZone, 'opp')}
    >
      <CardTile card={p.fieldZone} small />
      {#if !p.fieldZone}<span class="zlabel">Field</span>{/if}
    </div>
  </div>
{:else}
  <!-- Your half — your mat (Monster line on top, nearest the centre). -->
  <div class="mat you">
    <!-- front line: Field · Monsters · Graveyard -->
    <div
      class="slot field"
      class:drop={!p.fieldZone}
      class:armed={draggingFieldSpell}
      class:targetable={p.fieldZone && targetCandidates.includes(p.fieldZone.iid)}
      ondragover={(e) => e.preventDefault()}
      ondrop={onDropField}
      onclick={() => onClickFieldZone(p.fieldZone)}
      oncontextmenu={(e) => p.fieldZone && openContext(e, p.fieldZone, 'field')}
    >
      <CardTile card={p.fieldZone} small />
      {#if !p.fieldZone}<span class="zlabel">Field</span>{/if}
    </div>
    {#each p.monsterZones as slot, i (i)}
      <!-- One persistent slot per zone, so a dying monster's dissolve (an
           absolute overlay) never adds a grid cell mid-transition. -->
      <div
        class="slot mon"
        class:own={!!slot}
        class:drop={!slot}
        class:armed={!slot && (draggingMonster || placingMonster)}
        data-iid={slot?.iid}
        class:respondtarget={slot && responseTargets.has(slot.iid)}
        class:respondsource={slot && responseSources.has(slot.iid)}
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
          {#if phase === 'battle_phase' && attackTargets(slot.iid)}
            <span class="badge canatk" title="Can attack">⚔️</span>
          {/if}
        {:else}
          <CardTile card={null} small />
        {/if}
      </div>
    {/each}
    <div class="slot pile gy" class:targetable={gyTargetable} onclick={() => toggleGy('you')}>
      {#if p.graveyard.length}
        <CardTile card={p.graveyard[p.graveyard.length - 1]} faceDown small />
        <span class="count">{p.graveyard.length}</span>
      {/if}
      <span class="zlabel">Graveyard</span>
    </div>
    <!-- back line: Extra Deck · Spell & Trap · Deck -->
    <div class="slot pile extra">
      {#if p.extraCount}<div class="pileback"></div>
        <span class="count">{p.extraCount}</span>{/if}
      <span class="zlabel">Extra</span>
    </div>
    {#each p.spellTrapZones as slot, i}
      {#if slot}
        <div
          class="slot st"
          class:actionable={yourTurn && (canActivate(slot.iid) || canUnionUnequip(slot.iid))}
          class:targetable={targetCandidates.includes(slot.iid)}
          class:respondsource={responseSources.has(slot.iid)}
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
      {#if p.deckCount}<div class="pileback"></div>
        <span class="count">{p.deckCount}</span>{/if}
      <span class="zlabel">Deck</span>
    </div>
  </div>
{/if}

<style>
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
  @media (prefers-reduced-motion: reduce) {
    .slot.fxhit, .slot.fxhit::after { animation: none; }
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
  /* Sword marker over a monster that can declare an attack this Battle Phase. */
  .badge.canatk {
    position: absolute;
    top: 2px;
    left: 2px;
    z-index: 4;
    font-size: 16px;
    line-height: 1;
    filter: drop-shadow(0 1px 2px #000);
    pointer-events: none;
    animation: swordpulse 1s ease-in-out infinite;
  }
  @keyframes swordpulse {
    0%, 100% { transform: scale(1); }
    50% { transform: scale(1.18); }
  }
  @media (prefers-reduced-motion: reduce) {
    .badge.canatk { animation: none; }
  }
  .slot.selected {
    outline: 2px solid var(--success);
  }
  .slot.tribute {
    outline: 2px solid var(--accent);
  }
  .slot.targetable {
    outline: 2px solid var(--danger);
    cursor: crosshair;
  }
  .slot.st.actionable {
    cursor: pointer;
  }
  .slot.st.actionable:hover {
    outline: 2px solid var(--accent);
  }
  /* The Field zone is a corner fixture (not part of the central 2×5), so it gets
     the dark recessed look, distinguished by a slightly stronger edge. */
  .slot.field {
    position: relative;
    background: rgba(0, 0, 0, 0.45);
    box-shadow: inset 0 0 0 1px var(--line-strong);
  }
  .slot.field.armed {
    outline: 2px dashed var(--success);
    background: var(--success-dim);
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
    z-index: 3;
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
  /* Board glows while a response prompt is open (visible through the light backdrop). */
  .slot.respondtarget {
    outline: 2px solid var(--danger);
    box-shadow: 0 0 16px 3px color-mix(in srgb, var(--danger) 75%, transparent);
    border-radius: var(--r);
    animation: respondpulse 1.1s ease-in-out infinite;
  }
  .slot.respondsource {
    outline: 2px solid var(--accent);
    box-shadow: 0 0 16px 3px color-mix(in srgb, var(--accent) 70%, transparent);
    border-radius: var(--r);
    animation: respondpulse 1.1s ease-in-out infinite;
  }
  @keyframes respondpulse {
    0%, 100% { filter: brightness(1); }
    50% { filter: brightness(1.35); }
  }
  @media (prefers-reduced-motion: reduce) {
    .slot.respondtarget, .slot.respondsource { animation: none; }
  }
</style>
