<script lang="ts">
  import { onMount } from 'svelte';
  import Button from '../../components/Button.svelte';
  import Select from '../../components/Select.svelte';
  import TextField from '../../components/TextField.svelte';
  import TextArea from '../../components/TextArea.svelte';
  import Note from '../../components/Note.svelte';
  import { request, runJob, errorText, operationToken, type Project } from '../../lib/intelligence';
  let projects = $state<Project[]>([]);
  let name = $state(''); let roots = $state(''); let brief = $state('');
  let importProject = $state(''); let importPaths = $state(''); let importing = $state(false); let phase = $state('');
  let importController: AbortController | null = null;
  let error = $state(''); let notice = $state(''); let busy = $state(false); let alive = true;
  async function load() {
    try { const result = await request<{ projects: Project[] }>('context.projects'); if (alive) projects = result.projects; }
    catch (e) { if (alive) error = errorText(e); }
  }
  onMount(() => { void load(); return () => { alive = false; importController?.abort(); }; });
  async function importFiles() {
    if (importing || !importProject || !importPaths.trim()) return;
    const paths = importPaths.split('\n').map((path) => path.trim()).filter(Boolean);
    if (paths.length > 16 || paths.some((path) => !path.startsWith('/') || path.length > 2000)) {
      error = 'Choose up to 16 absolute file paths, each no longer than 2,000 characters.'; return;
    }
    importing = true; error = ''; importController = new AbortController();
    try {
      const result = await runJob<{ imported: number }>('context.import_files', { project_id: importProject, paths }, importController.signal, (job) => { if (alive) phase = job.phase || job.status; });
      if (alive) { notice = `${result.imported} approved sources imported.`; importPaths = ''; }
    } catch (e) { if (alive) error = e instanceof DOMException && e.name === 'AbortError' ? 'Import cancelled.' : errorText(e); }
    finally { if (alive) importing = false; }
  }
  async function create() {
    if (!name.trim() || !roots.trim() || busy) return;
    busy = true; error = '';
    try {
      await request('context.create_project', { name, roots: roots.split('\n').map((r) => r.trim()).filter(Boolean), brief, operation_token: operationToken() });
      if (alive) { name = ''; roots = ''; brief = ''; notice = 'Project created. Select it explicitly in a workspace or test preview.'; await load(); }
    } catch (e) { if (alive) error = errorText(e); }
    finally { if (alive) busy = false; }
  }
</script>
<section class="projects">
  <h2 class="serif">Projects</h2><p class="hint">Choose the work a prompt belongs to. An app name or the last project used does not establish its identity.</p>
  {#if error}<Note tone="warning" text={error} />{/if}{#if notice}<Note tone="info" text={notice} />{/if}
  <form onsubmit={(e) => { e.preventDefault(); void create(); }}>
    <h3>Add a project</h3><TextField label="Project name" bind:value={name} disabled={busy} />
    <TextArea label="Approved local folders (one absolute path per line)" rows={3} bind:value={roots} disabled={busy} placeholder="Enter the approved local folder for this project." required />
    <TextArea label="Pinned project brief" rows={4} bind:value={brief} disabled={busy} placeholder="The purpose, stack, and constraints relevant to this project." />
    <p class="hint">Approved folders bound the native reader’s read-only access. Creating a project does not import the folder’s contents. Import selected files below; the model cannot widen the approved scope.</p>
    <div><Button variant="primary" type="submit" busy={busy} disabled={!name.trim() || !roots.trim()}>Create project</Button></div>
  </form>
  {#if projects.length}<details class="import"><summary>Import approved project files</summary>
    <p class="hint">Import up to 16 selected text, Markdown, or JSON files relevant to the prompt. Enter absolute file paths within the selected project’s approved roots. Folders are not crawled.</p>
    <form onsubmit={(e) => { e.preventDefault(); void importFiles(); }}>
      <Select label="Project for these sources" value={importProject} disabled={importing} options={[{ value: '', label: 'Choose a project' }, ...projects.map((project) => ({ value: project.id, label: project.name }))]} onchange={(v) => importProject = v} />
      <TextArea label="Selected file paths (one per line)" rows={4} bind:value={importPaths} disabled={importing} required />
      <div><Button type="submit" busy={importing} disabled={!importProject || !importPaths.trim()}>Import selected paths</Button>{#if importing}<Button size="sm" onclick={() => importController?.abort()}>Cancel</Button><span role="status">{phase}</span>{/if}</div>
    </form>
  </details>{/if}
  <div class="project-list">{#each projects as project (project.id)}<article><h3>{project.name}</h3>{#if project.brief}<p class="brief selectable">{project.brief}</p>{/if}<details><summary>Approved sources and identity</summary>{#each project.roots ?? [] as root}<p class="root selectable">{root}</p>{:else}<p class="hint">No folder roots approved.</p>{/each}<p class="hint">Revision {project.revision}. The native resolver retains workspace identity separately for each worktree.</p></details></article>{:else}<p class="hint">No projects yet. Source-only transformations remain available.</p>{/each}</div>
</section>
<style>
  .projects { padding-top: 26px; } h2 { font-size: var(--display-sm); } h3 { font-size: var(--text-lg); font-weight: 600; }
  .hint { color: var(--text-2); font-size: var(--text-base); line-height: 1.5; margin: 10px 0 18px; }
  form { display: grid; gap: 16px; padding: 22px; background: var(--surface); border: 1px solid var(--hairline); border-radius: var(--radius-md); margin-top: 24px; }
  .project-list { margin-top: 24px; } article { border-top: 1px solid var(--hairline); padding: 20px 0; }
  .brief { white-space: pre-wrap; margin: 12px 0; font-size: var(--text-md); line-height: 1.6; }
  .import { margin-top: 24px; }
  details { margin-top: 14px; } summary { cursor: pointer; font-size: var(--text-base); } .root { font-size: var(--text-base); overflow-wrap: anywhere; margin-top: 10px; }
</style>
