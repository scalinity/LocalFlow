<script lang="ts">
  import TextField from '../../components/TextField.svelte';
  import Button from '../../components/Button.svelte';
  let { initial, busy, onapply }: { initial: string; busy: boolean; onapply: (v: string) => void } = $props();
  let value = $state(initial);
</script>

<div class="field">
  <TextField label="Keep usage for" hideLabel size="sm" bind:value />
  <Button size="sm" {busy} onclick={() => onapply(value)}>Apply</Button>
</div>

<style>
  .field {
    display: flex;
    align-items: center;
    gap: 8px;
    width: 190px;
    flex: none;
  }
</style>
