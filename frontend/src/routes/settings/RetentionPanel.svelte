<script lang="ts">
  import TextField from '../../components/TextField.svelte';
  import Button from '../../components/Button.svelte';

  // Mounted once the retention policy has loaded: the fields start from
  // it and are the user's own from then on (a refresh never rewrites
  // what is being typed — the AppKit Hub's rule).
  let { retention, busy, onapply }: { retention: Record<string, number | null>; busy: boolean; onapply: (v: Record<string, string>) => void } = $props();

  const KEYS = ['transcript', 'audio_success', 'audio_failed', 'metadata', 'training_buffer'] as const;
  const LABEL: Record<string, [string, string]> = {
    transcript: ['Transcripts', 'How long dictated text is kept in History.'],
    audio_success: ['Recordings', 'Audio of dictations that were inserted.'],
    audio_failed: ['Failed recordings', 'Audio kept so a failed dictation can be retried.'],
    metadata: ['Dictation records', 'Times, apps and outcomes without their text.'],
    training_buffer: ['Training evidence', 'Examples collected for review and export.'],
  };
  const initial = Object.fromEntries(KEYS.map((k) => [k, retention?.[k] != null ? String(retention[k]) : '']));
  let values = $state<Record<string, string>>(initial);
</script>

<div class="panel">
  {#each KEYS as k (k)}
    <div class="row">
      <div><p class="label">{LABEL[k][0]}</p><p class="desc">{LABEL[k][1]}</p></div>
      <div class="days">
        <TextField label="{LABEL[k][0]} (days)" hideLabel size="sm" bind:value={values[k]} inputmode="numeric" />
        <span class="unit">days</span>
      </div>
    </div>
  {/each}
</div>
<div class="apply"><Button variant="primary" {busy} onclick={() => onapply({ ...values })}>Apply retention</Button></div>

<style>
  .panel {
    background: var(--card);
    border-radius: var(--radius-lg);
    padding: 4px 28px;
  }
  .row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 24px;
    min-height: 72px;
    padding: 14px 0;
  }
  .row + .row {
    border-top: 1px solid var(--hairline);
  }
  .label {
    font-size: var(--text-lg);
    font-weight: 500;
  }
  .desc {
    margin-top: 3px;
    font-size: var(--text-md);
    color: var(--text-2);
  }
  .days {
    display: flex;
    align-items: center;
    gap: 8px;
    width: 150px;
    flex: none;
  }
  .unit {
    color: var(--text-2);
    font-size: var(--text-base);
  }
  .apply {
    margin-top: 18px;
    display: flex;
    justify-content: flex-end;
  }
</style>
