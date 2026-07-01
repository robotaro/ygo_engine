<script>
  // A compact per-player phase tracker shown in each player's LP bar (GBA-style).
  // `active` is true for whoever's turn it is — only then is the current phase lit.
  let { phases = [], index = -1, active = false } = $props()
</script>

<div class="strip" class:active>
  {#each phases as p, i}
    <span class="ps" class:on={active && i === index} class:done={active && i < index}
      title={p.label}>{p.short}</span>
  {/each}
</div>

<style>
  .strip {
    display: inline-flex;
    gap: 2px;
    align-items: center;
  }
  .ps {
    font-size: 10px;
    font-weight: 800;
    letter-spacing: 0.02em;
    color: var(--faint);
    padding: 2px 5px;
    border-radius: var(--r-pill);
    transition: all 0.12s ease;
  }
  .strip:not(.active) .ps {
    opacity: 0.5;
  }
  .ps.done {
    color: var(--muted);
  }
  .ps.on {
    background: var(--accent);
    color: var(--accent-ink);
    box-shadow: 0 0 0 2px var(--warn-dim);
  }
</style>
