<script lang="ts">
  let { collapsed = false }: { collapsed?: boolean } = $props();
</script>

<div class="brand" class:collapsed>
  <svg class="mark" viewBox="0 0 22 22" aria-hidden="true">
    <rect x="2" y="8" width="2.4" height="6" rx="1.2" />
    <rect x="6.2" y="4" width="2.4" height="14" rx="1.2" />
    <rect x="10.4" y="7" width="2.4" height="8" rx="1.2" />
    <rect x="14.6" y="2.5" width="2.4" height="17" rx="1.2" />
    <rect x="18.8" y="6.5" width="2.4" height="9" rx="1.2" />
  </svg>
  {#if !collapsed}<span class="word">LocalFlow</span>{/if}
</div>

<style>
  .brand {
    display: flex;
    align-items: center;
    gap: 9px;
    height: 34px;
    padding: 0 12px;
  }
  .brand.collapsed {
    justify-content: center;
    padding: 0;
  }
  .mark {
    width: 23px;
    height: 23px;
    fill: var(--text);
    flex: none;
  }
  .word {
    font-size: 19px;
    font-weight: 650;
    letter-spacing: -0.02em;
  }
</style>
