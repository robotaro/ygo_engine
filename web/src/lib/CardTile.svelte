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

  // A monster slot reports faceDown + a null name when hidden from us.
  let hidden = $derived(faceDown || (card && card.name == null))
  let accent = $derived(card && card.attribute ? ATTR_COLORS[card.attribute] : '#4a4a55')
  // Tributes needed to Normal Summon: 1-4 none, 5-6 one, 7+ two.
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
    title={card.text || ''}
  >
    <div class="name">{card.name}</div>
    {#if card.cardType === 'monster'}
      <div class="lvline">
        {#if card.level != null}<span class="lv">Lv{card.level}</span>{/if}
        {#if tributeCost > 0}
          <span class="trib" title={`Requires ${tributeCost} Tribute(s) to Normal Summon`}>
            ✦{tributeCost}
          </span>
        {/if}
      </div>
      <div class="stats">
        <span class="atk">{card.attack ?? '?'}</span>
        <span class="slash">/</span>
        <span class="def">{card.defense ?? '?'}</span>
      </div>
    {:else}
      <div class="kind">{card.cardType}</div>
    {/if}
  </div>
{/if}

<style>
  .tile {
    width: 84px;
    height: 118px;
    border-radius: 7px;
    box-sizing: border-box;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
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
    border: 2px solid var(--accent);
    background: linear-gradient(160deg, #2b2b33, #1c1c22);
    padding: 5px;
    color: #f3f3f3;
    box-shadow: 0 2px 6px rgba(0, 0, 0, 0.4);
  }
  .rot {
    transform: rotate(90deg);
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
  .lvline {
    display: flex;
    gap: 4px;
    align-items: center;
    font-size: 9px;
  }
  .lv {
    color: #ffcf5c;
    font-weight: 700;
  }
  .trib {
    background: #c0651c;
    color: #fff;
    font-weight: 800;
    border-radius: 3px;
    padding: 0 4px;
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
