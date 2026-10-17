import './styles.css';
import { backend, mock } from './backend';
import { diff, marks } from './diff';
import type { Choice, Pair, Progress, Snapshot } from './types';
const $ = <T extends HTMLElement = HTMLElement>(id: string) => document.getElementById(id) as T;
let state: Snapshot;
let busy=false, paused=false, sourceView=false, marksOn=true, guideOpen=false, noteOpen=false, broken=false;
let shown='';
let started=performance.now(), elapsed=0;
let noteWrites: Promise<void> = Promise.resolve();
const current = () => state?.pairs.find(p => p.pair_id === state.queue[0]);
const seconds = () => elapsed + (paused ? 0 : (performance.now()-started)/1000);
const resetTimer = () => { elapsed=0; started=performance.now(); };
const status = (message: string) => { $('status').textContent=message; };
const hint = (label: string, key: string) => { const k=document.createElement('kbd'); k.textContent=key; return [`${label} `, k]; };
$('mode').textContent = mock ? 'Toy session' : '';
$('real-session').hidden = !mock;
// One tick per pair, in sets of 25. Ticks count judgments and never show which side won.
function ledger(p: Progress) {
  const root=$('ledger');
  if (root.dataset.total !== String(p.total)) {
    root.dataset.total=String(p.total);
    const sets=[];
    for (let i=0; i<p.total; i+=25) {
      const set=document.createElement('span'); set.className='set';
      const n=Math.min(25,p.total-i); set.style.flexGrow=String(n);
      for (let j=0; j<n; j++) set.append(document.createElement('i'));
      sets.push(set);
    }
    root.replaceChildren(...sets);
  }
  root.querySelectorAll('i').forEach((tick,i) => { tick.className=i < p.completed ? 'done' : i === p.completed ? 'next' : ''; });
}
// Step the type down until the source and both panes fit; past the last step they scroll inside.
const scrollers=['source-band','a-text','b-text','candidates'];
const overflows = (id: string) => { const e=$(id); return e.scrollHeight > e.clientHeight+1; };
// A soft fade at the bottom edge says there is more, until the end is in view.
const edge = (id: string) => { const e=$(id); e.classList.toggle('more', e.scrollTop+e.clientHeight < e.scrollHeight-2); };
function fit() {
  const ws=$('workspace'); if (ws.hidden) return;
  for (const size of ['0','1','2']) {
    ws.dataset.size=size;
    if (!scrollers.some(overflows)) break;
  }
  scrollers.forEach(edge);
}
for (const id of scrollers) $(id).addEventListener('scroll', () => edge(id), {passive:true});
// Pairs run from a few hundred to several thousand characters, so time left scales with what is still to read.
// Fewer than ten judgments say too little about pace to estimate from.
const size = (x: Pair) => x.source.length + x.a.text.length + x.b.text.length;
function estimate(p: Progress) {
  if (p.median_seconds === null || p.completed < 10) return 'Time estimate after 10 pairs';
  const left=new Set(state.queue);
  const done=state.pairs.filter(x => !left.has(x.pair_id)).map(size).sort((a,b) => a-b);
  const typical=(done[Math.floor((done.length-1)/2)] + done[Math.floor(done.length/2)])/2;
  const minutes=p.median_seconds*state.pairs.filter(x => left.has(x.pair_id)).reduce((t,x) => t+size(x),0)/typical/60;
  if (minutes < 20) return `about ${Math.max(1,Math.round(minutes))} min left`;
  const rounded=Math.round(minutes/5)*5;
  return rounded < 60 ? `about ${rounded} min left` : `about ${Math.floor(rounded/60)} h${rounded%60 ? ` ${rounded%60} min` : ''} left`;
}
function render() {
  $('session-line').hidden=false; $('ledger').hidden=false;
  $('save-label').textContent = mock ? 'Toy data, kept in memory only' : 'Saved after every choice';
  const pair=current();
  const p=state.progress;
  $('progress').textContent=`${p.completed} of ${p.total}`;
  $('estimate').textContent=!pair ? 'All pairs reviewed' : estimate(p);
  ledger(p);
  const working=!!pair && !paused;
  $('workspace').hidden=!working; $('decision').hidden=!working;
  $('paused').hidden=!paused;
  $('summary').hidden=!!pair || paused;
  $('pause').hidden=!pair;
  $('pause').replaceChildren(...hint(paused ? 'Continue' : 'Pause','Esc'));
  for (const id of ['undo','summary-undo']) $<HTMLButtonElement>(id).disabled=!state.can_undo;
  const showMarks=marksOn && !sourceView;
  $('marks').setAttribute('aria-pressed',String(showMarks)); $('diff').setAttribute('aria-pressed',String(sourceView));
  $('marks-help').hidden=!showMarks; $('diff-help').hidden=!sourceView;
  $('ladder').hidden=!guideOpen; $('guide').setAttribute('aria-expanded',String(guideOpen));
  if (pair) {
    $('source').textContent=pair.source;
    if (sourceView) for (const side of ['a','b'] as const) $(`${side}-text`).replaceChildren(diff(pair.source,pair[side].text));
    else if (showMarks) { const [a,b]=marks(pair.a.text,pair.b.text); $('a-text').replaceChildren(a); $('b-text').replaceChildren(b); }
    else for (const side of ['a','b'] as const) $(`${side}-text`).textContent=pair[side].text;
    $('vocabulary').textContent=pair.vocabulary.length ? `Vocabulary: ${pair.vocabulary.map(([a,b]) => `${a} → ${b}`).join(', ')}` : '';
    $<HTMLTextAreaElement>('note').value=state.drafts[pair.pair_id] ?? '';
    $('note-panel').hidden=!noteOpen;
    $('note-preview').hidden=noteOpen || !state.drafts[pair.pair_id];
    $('note-preview').textContent=state.drafts[pair.pair_id] ? `Note: ${state.drafts[pair.pair_id]}` : '';
    if (pair.pair_id !== shown && working) {
      shown=pair.pair_id;
      for (const id of ['source-band','a-text','b-text','candidates']) $(id).scrollTop=0;
      const ws=$('workspace'); ws.classList.remove('fresh'); void ws.offsetWidth; ws.classList.add('fresh');
    }
    fit();
  } else if (!paused) {
    $('summary-time').textContent=p.median_seconds === null ? 'No judgments yet.' : `${p.completed} judgments, ${p.median_seconds.toFixed(1)} seconds median per pair.`;
    $('counts').replaceChildren(...(['a','b','tie','both_wrong'] as const).map(choice => {
      const group=document.createElement('div'); const dt=document.createElement('dt'); const dd=document.createElement('dd');
      dt.textContent=({a:'A better',b:'B better',tie:'Tie',both_wrong:'Both wrong'})[choice]; dd.textContent=String(p.counts[choice]); group.append(dt,dd); return group;
    }));
  }
}
function fail(error?: unknown, opening=false) {
  const missing = opening && error === 'PAIRS_MISSING';
  broken=true; paused=true; $('workspace').hidden=true; $('decision').hidden=true; $('paused').hidden=true; $('summary').hidden=true;
  $('pause').hidden=true;
  $('session-line').hidden=opening;
  $('ledger').hidden=opening;
  $('failure').hidden=false;
  $('failure-title').textContent=missing ? 'Waiting for review pairs.' : 'Couldn’t open this session.';
  $('failure-text').textContent=missing
    ? 'The blinded pairs haven’t been prepared yet. Once they’re ready, choose Check again. You can try the controls with toy pairs in the meantime.'
    : 'The session could not be opened safely. Check the configured files and try again. Existing saved judgments remain on disk.';
  $('retry').textContent=missing ? 'Check again' : 'Try again';
  $('try-toy').hidden=!missing;
  $('toy-explanation').hidden=!missing;
  $('save-label').textContent=opening ? 'No session open' : 'Review stopped';
  status(missing ? 'Waiting for input.' : 'Session unavailable.');
  if (opening) $('retry').focus();
}
async function load() {
  busy=true;
  try {
    state=await backend.load(); broken=false; noteWrites=Promise.resolve(); paused=false; $('failure').hidden=true;
    // The guide opens by itself only before the first judgment.
    guideOpen=state.progress.completed === 0;
    resetTimer(); render(); status('');
  }
  catch (error) { fail(error, true); } finally { busy=false; }
}
async function action(run: () => Promise<Snapshot>, message: string, judged=false) {
  if (busy || broken) return;
  busy=true;
  try {
    await noteWrites;
    state=await run(); noteOpen=false; resetTimer();
    const set=judged && state.progress.completed > 0 && state.progress.completed % 25 === 0 && !!current();
    $('notice').hidden=!set;
    $('notice').textContent=set ? `That finishes a set of 25. A good moment for a short break; Esc pauses.` : '';
    render();
    status(set ? $('notice').textContent! : message);
  } catch { fail(); } finally { busy=false; }
}
// The one moment of motion: the chosen button confirms, then the next pair fades in.
function confirm(choice: Choice) {
  const button=document.querySelector<HTMLButtonElement>(`[data-choice="${choice}"]`);
  if (!button) return;
  button.classList.add('chosen'); setTimeout(() => button.classList.remove('chosen'),160);
}
function judge(choice: Choice) {
  const pair=current(); if (!pair || paused || noteOpen || busy || broken) return;
  const spent=seconds(); const note=state.drafts[pair.pair_id] ?? '';
  confirm(choice);
  void action(() => backend.judge(pair.pair_id,choice,note,spent), mock ? 'Choice recorded in memory.' : 'Choice saved.', true);
}
function undo() { if (!paused && state?.can_undo) void action(() => backend.undo(),'Last judgment undone.'); }
function skip() { const pair=current(); if (pair && !paused && !noteOpen) void action(() => backend.skip(pair.pair_id),'Set aside. This pair returns at the end.'); }
function openNote() { if (!current() || busy || paused) return; noteOpen=true; render(); $('note').focus(); }
// Shortcuts never move focus onto a button: focus moved after a key press draws the keyboard ring.
// The hidden note box is blurred so it cannot keep swallowing shortcuts.
function closeNote() { noteOpen=false; $('note').blur(); render(); }
function pause() {
  if (!current() || busy || broken) return;
  if (!paused) elapsed=seconds(); else started=performance.now();
  paused=!paused; render();
}
function toggleDiff() { if (!paused && current() && !busy) { sourceView=!sourceView; render(); } }
function toggleMarks() { if (!paused && current() && !busy) { marksOn=sourceView ? true : !marksOn; sourceView=false; render(); } }
function toggleGuide() {
  if (paused || !current()) return;
  const inside=$('ladder').contains(document.activeElement);
  guideOpen=!guideOpen; render();
  if (!guideOpen && inside) $('guide').focus();
}
for (const button of document.querySelectorAll<HTMLButtonElement>('[data-choice]')) button.onclick=() => judge(button.dataset.choice as Choice);
$('undo').onclick=undo; $('summary-undo').onclick=undo; $('skip').onclick=skip; $('add-note').onclick=openNote; $('note-done').onclick=closeNote;
$('pause').onclick=pause; $('resume').onclick=pause; $('diff').onclick=toggleDiff; $('marks').onclick=toggleMarks; $('retry').onclick=() => void load();
$('guide').onclick=toggleGuide; $('ladder-close').onclick=toggleGuide;
$('try-toy').onclick=() => { location.search='?mock=1'; };
$('real-session').onclick=() => { location.search=''; };
$('note').oninput=() => {
  const id=current()!.pair_id; const note=$<HTMLTextAreaElement>('note').value; state.drafts[id]=note;
  noteWrites=noteWrites.then(() => backend.draft(id,note));
  void noteWrites.catch(() => fail());
};
$('export').onclick=async () => {
  if (busy) return; busy=true;
  try { await backend.export(); $('export-status').textContent=mock ? 'Toy summary downloaded.' : 'summary.json saved beside the annotations.'; }
  catch { $('export-status').textContent='Summary could not be saved. Your judgments are still saved.'; } finally { busy=false; }
};
// Pointing at a mark lights up its counterpart in the other pane.
const link = (e: Event, on: boolean) => {
  const mark=(e.target as Element).closest?.('mark[data-op]') as HTMLElement | null;
  if (mark) document.querySelectorAll(`#candidates mark[data-op="${mark.dataset.op}"]`).forEach(m => m.classList.toggle('linked',on));
};
$('candidates').addEventListener('mouseover', e => link(e,true));
$('candidates').addEventListener('mouseout', e => link(e,false));
// When a pane does overflow, the other follows it proportionally.
let leader='', leading=0;
for (const [from,to] of [['a-text','b-text'],['b-text','a-text']]) $(from).addEventListener('scroll', () => {
  if (leader && leader !== from && performance.now() < leading) return; // the follower's echo
  leader=from; leading=performance.now()+120;
  const a=$(from), b=$(to); const range=a.scrollHeight-a.clientHeight;
  if (range > 0 && b.scrollHeight > b.clientHeight) b.scrollTop=a.scrollTop/range*(b.scrollHeight-b.clientHeight);
});
let fitting=0;
window.addEventListener('resize', () => { cancelAnimationFrame(fitting); fitting=requestAnimationFrame(fit); });
document.addEventListener('keydown', e => {
  if (e.repeat || e.isComposing || e.metaKey || e.ctrlKey || e.altKey || busy || broken) return;
  if (e.target instanceof HTMLTextAreaElement || e.target instanceof HTMLInputElement) return;
  const key=e.key.toLowerCase();
  if (!['a','arrowleft','b','arrowright','t','arrowdown','w','u','n','s','d','m','?'].includes(key)) return;
  e.preventDefault();
  if (paused) return;
  if (key==='u') undo(); else if (key==='n') openNote(); else if (key==='s') skip(); else if (key==='d') toggleDiff();
  else if (key==='m') toggleMarks(); else if (key==='?') toggleGuide();
  else judge(({a:'a',arrowleft:'a',b:'b',arrowright:'b',t:'tie',arrowdown:'tie',w:'both_wrong'} as Record<string,Choice>)[key]);
});
// The macOS web view consumes Escape's keydown as a cancel command and delivers only the keyup,
// so Escape is handled on keyup everywhere: a note first, then the guide, then pause.
document.addEventListener('keyup', e => {
  if (e.key !== 'Escape' || e.isComposing || e.metaKey || e.ctrlKey || e.altKey || busy || broken) return;
  e.preventDefault();
  if (e.target instanceof HTMLTextAreaElement || e.target instanceof HTMLInputElement) closeNote();
  else if (guideOpen && !paused) toggleGuide();
  else pause();
});
// Time away from the window must not inflate annotation time.
document.addEventListener('visibilitychange', () => { if (document.hidden && state && !paused) pause(); });
void load();
