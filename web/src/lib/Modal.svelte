<script>
  // Reusable modal shell: a dimmed backdrop that closes on click or Escape, with
  // the content centred and click-through stopped inside. Callers supply their
  // own panel element (with its own scoped styles) as the default children; this
  // just centralises the backdrop + the (previously inconsistent) Escape handling.
  let { onclose = () => {}, closeOnBackdrop = true, children } = $props()

  function onKey(e) {
    if (e.key === 'Escape') onclose()
  }
</script>

<svelte:window onkeydown={onKey} />

<!-- svelte-ignore a11y_click_events_have_key_events -->
<!-- svelte-ignore a11y_no_static_element_interactions -->
<div class="backdrop" role="presentation" onclick={() => closeOnBackdrop && onclose()}>
  <!-- display:contents wrapper: no box of its own, so the caller's panel is the
       flex child and keeps its own sizing — it only exists to stop click-through. -->
  <div class="stop" onclick={(e) => e.stopPropagation()}>
    {@render children?.()}
  </div>
</div>

<style>
  .backdrop {
    position: fixed;
    inset: 0;
    z-index: 100;
    background: rgba(0, 0, 0, 0.7);
    display: flex;
    align-items: center;
    justify-content: center;
  }
  .stop {
    display: contents;
  }
</style>
