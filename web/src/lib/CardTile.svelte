<script>
  let { card = null, faceDown = false, defense = false, small = false } = $props()

  const ATTR_COLORS = {
    DARK: '#6b3fa0',
    LIGHT: '#c9a227',
    EARTH: '#8a6d3b',
    WATER: '#2b6cb0',
    FIRE: '#c0392b',
    WIND: '#2f9e57',
    DIVINE: '#b8860b',
  }

  let hidden = $derived(faceDown || (card && card.name == null))
  let accent = $derived(card && card.attribute ? ATTR_COLORS[card.attribute] : '#4a4a55')
  let tributeCost = $derived(
    card && card.cardType === 'monster' && card.level
      ? card.level <= 4
        ? 0
        : card.level <= 6
          ? 1
          : 2
      : 0,
  )
</script>

{#if !card}
  <div class="tile empty" class:small></div>
{:else if hidden}
  <div class="tile back" class:small class:rot={defense}>
    <div class="back-emblem">YGO</div>
  </div>
{:else}
  <div
    class="tile card"
    class:small
    class:rot={defense}
    style="--accent:{accent}"
    title={card.text || card.name}
  >
    <!-- Text fallback (shown if there is no art, or the art fails to load). -->
    <div class="name">{card.name}</div>
    {#if card.cardType === 'monster'}
      {#if card.level != null}<div class="lv">Lv{card.level}</div>{/if}
      <div class="stats">
        <span class="atk">{card.attack ?? '?'}</span><span class="slash">/</span><span
          class="def">{card.defense ?? '?'}</span>
      </div>
    {:else}
      <div class="kind">{card.cardType}</div>
    {/if}

    {#if card.imageId}
      <img
        class="art"
        src={`/cards/${card.imageId}.jpg`}
        alt={card.name}
        onerror={(e) => e.currentTarget.remove()}
      />
    {/if}

    <!-- Legibility overlays, above the art. -->
    {#if tributeCost > 0}
      <span class="trib" title={`Requires ${tributeCost} Tribute(s)`}>✦{tributeCost}</span>
    {/if}
    {#if card.cardType === 'monster'}
      {@const shown = defense ? (card.effDef ?? card.defense) : (card.effAtk ?? card.attack)}
      {@const base = defense ? card.defense : card.attack}
      <span class="stat-badge" class:boosted={shown > base} class:weakened={shown < base}>
        {shown}
      </span>
    {/if}
  </div>
{/if}

<style>
  .tile {
    width: 84px;
    height: 118px;
    border-radius: 7px;
    box-sizing: border-box;
    user-select: none;
  }
  .tile.small {
    width: 64px;
    height: 90px;
  }
  .empty {
    border: 1px dashed #3a3a45;
    background: rgba(255, 255, 255, 0.02);
  }
  .card {
    position: relative;
    overflow: hidden;
    border: 2px solid var(--accent);
    background: linear-gradient(160deg, #2b2b33, #1c1c22);
    padding: 5px;
    color: #f3f3f3;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    box-shadow: 0 2px 6px rgba(0, 0, 0, 0.4);
  }
  .rot {
    transform: rotate(90deg);
  }
  .art {
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
    object-fit: cover;
    border-radius: 5px;
    z-index: 1;
  }
  .name {
    font-size: 10px;
    font-weight: 700;
    line-height: 1.1;
    overflow: hidden;
    display: -webkit-box;
    -webkit-line-clamp: 3;
    -webkit-box-orient: vertical;
  }
  .lv {
    font-size: 8px;
    color: #ffcf5c;
    font-weight: 700;
  }
  .stats {
    font-size: 11px;
    font-weight: 700;
    text-align: right;
  }
  .atk {
    color: #ff8a7a;
  }
  .def {
    color: #8ab6ff;
  }
  .slash {
    color: #888;
  }
  .kind {
    font-size: 9px;
    text-transform: uppercase;
    color: #bdbdbd;
    text-align: right;
  }
  /* overlays sit above the art */
  .trib {
    position: absolute;
    top: 2px;
    right: 2px;
    z-index: 2;
    background: #c0651c;
    color: #fff;
    font-size: 9px;
    font-weight: 800;
    border-radius: 3px;
    padding: 0 3px;
  }
  .stat-badge {
    position: absolute;
    bottom: 2px;
    right: 2px;
    z-index: 2;
    background: rgba(0, 0, 0, 0.78);
    color: #ffd9a0;
    font-size: 10px;
    font-weight: 800;
    border-radius: 3px;
    padding: 0 4px;
  }
  .stat-badge.boosted {
    color: #7dff9e;
  }
  .stat-badge.weakened {
    color: #ff8a7a;
  }
  .back {
    border: 2px solid #7a5c1e;
    background: repeating-linear-gradient(45deg, #4a3a14, #4a3a14 6px, #5a4a1e 6px, #5a4a1e 12px);
    display: flex;
    align-items: center;
    justify-content: center;
  }
  .back-emblem {
    font-size: 13px;
    font-weight: 800;
    color: #d9bf7a;
    letter-spacing: 1px;
    opacity: 0.7;
  }
</style>
