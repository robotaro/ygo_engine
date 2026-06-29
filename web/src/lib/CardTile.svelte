<script>
  import cardBack from '../assets/card_back.jpg'

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

  // A card shows its back when it's Set face-down, or when the server withheld
  // its identity (an opponent's face-down card arrives with no name).
  let dataHidden = $derived(card != null && card.name == null)
  let showBack = $derived(faceDown || dataHidden)
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

  // Compose the position turn (90° for Defense) with the face-down/up flip, so a
  // Set monster revealed into Attack animates the turn and the flip in one move.
  let transform = $derived(`rotate(${defense ? 90 : 0}deg) rotateY(${showBack ? 0 : 180}deg)`)
</script>

{#if !card}
  <div class="tile empty" class:small></div>
{:else}
  <div class="tile" class:small>
    <div class="flip" style="transform: {transform}">
      <!-- Back face: the real card back, shown while the card is face-down. -->
      <div class="face back" title={card.name ?? 'Face-down card'}>
        <img class="backimg" src={cardBack} alt="Face-down card" />
      </div>

      <!-- Front face -->
      <div class="face front card" style="--accent:{accent}" title={card.text || card.name}>
        {#if card.name != null}
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
        {/if}
      </div>
    </div>
  </div>
{/if}

<style>
  .tile {
    width: 84px;
    height: 118px;
    border-radius: 7px;
    box-sizing: border-box;
    user-select: none;
    perspective: 700px;
    transition:
      transform 0.16s ease,
      box-shadow 0.16s ease;
  }
  .tile.small {
    width: 64px;
    height: 90px;
  }
  .empty {
    border: 1px dashed #3a3a45;
    background: rgba(255, 255, 255, 0.02);
  }
  /* Full-size hand cards lift toward the player on hover. */
  .tile:not(.small):not(.empty):hover {
    transform: translateY(-7px) scale(1.05);
    box-shadow: 0 10px 22px rgba(0, 0, 0, 0.55);
    z-index: 5;
  }

  /* The two faces share a 3D space; rotating .flip turns the card over. */
  .flip {
    position: absolute;
    inset: 0;
    transform-style: preserve-3d;
    transition: transform 0.45s cubic-bezier(0.2, 0.7, 0.25, 1);
    will-change: transform;
  }
  .face {
    position: absolute;
    inset: 0;
    border-radius: 7px;
    overflow: hidden;
    backface-visibility: hidden;
    -webkit-backface-visibility: hidden;
  }
  .face.front {
    transform: rotateY(180deg);
  }

  .back {
    background: #0a0a08;
    border: 1px solid #5a4a1e;
  }
  .backimg {
    width: 100%;
    height: 100%;
    object-fit: cover;
    display: block;
  }

  .card {
    border: 2px solid var(--accent);
    background: linear-gradient(160deg, #2b2b33, #1c1c22);
    padding: 5px;
    color: #f3f3f3;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    box-shadow: 0 2px 6px rgba(0, 0, 0, 0.4);
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

  @media (prefers-reduced-motion: reduce) {
    .tile,
    .flip {
      transition: none;
    }
    .tile:not(.small):not(.empty):hover {
      transform: none;
    }
  }
</style>
