import { test, expect } from '@playwright/test';
import { mkdirSync, readFileSync } from 'node:fs';
import type { Page } from '@playwright/test';
const screenshotDir='verification/screenshots';
mkdirSync(screenshotDir,{recursive:true});
const toy=JSON.parse(readFileSync('src/mock-pairs.json','utf8')) as {source:string;a:{text:string};b:{text:string}}[];
const total=toy.length;
async function tabTo(page:Page,id:string) {
  for(let n=0;n<25;n++) {
    if(await page.evaluate(() => document.activeElement?.id)===id) return;
    await page.keyboard.press('Tab');
  }
  throw Error(`Keyboard could not reach ${id}`);
}
async function open(page:Page) {
  await page.goto('/?mock=1');
  await expect(page.locator('#workspace')).toBeVisible();
}
// The whole review fits the window: the page never scrolls and every choice stays on screen.
async function expectFits(page:Page) {
  const fit=await page.evaluate(() => ({h:document.scrollingElement!.scrollHeight,ih:innerHeight,w:document.scrollingElement!.scrollWidth,iw:innerWidth}));
  expect(fit.h).toBeLessThanOrEqual(fit.ih); expect(fit.w).toBeLessThanOrEqual(fit.iw);
  const bar=(await page.locator('#decision').boundingBox())!;
  expect(bar.y).toBeGreaterThanOrEqual(0); expect(bar.y+bar.height).toBeLessThanOrEqual(fit.ih+0.5);
  for (const choice of ['a','b','tie','both_wrong']) await expect(page.locator(`[data-choice="${choice}"]`)).toBeInViewport({ratio:1});
}
const inside=(page:Page,id:string) => page.evaluate(i => { const e=document.getElementById(i)!; return e.scrollHeight <= e.clientHeight+1; }, id);

test('the guide opens before the first judgment; ? toggles it and Esc closes it before pausing',async({page})=>{
  await open(page);
  await expect(page.locator('#ladder')).toBeVisible();
  await expect(page.locator('#guide')).toHaveAttribute('aria-expanded','true');
  await expect(page.locator('#ladder li')).toHaveCount(4);
  await expect(page.locator('#ladder li').first()).toContainText('Damage first');
  await page.screenshot({path:`${screenshotDir}/guide.png`});
  await page.keyboard.press('?');
  await expect(page.locator('#ladder')).toBeHidden();
  await expect(page.locator('#guide')).toHaveAttribute('aria-expanded','false');
  await page.keyboard.press('?');
  await expect(page.locator('#ladder')).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(page.locator('#ladder')).toBeHidden();
  await expect(page.locator('#paused')).toBeHidden();
  await page.keyboard.press('Escape');
  await expect(page.locator('#paused')).toBeVisible();
  await page.keyboard.press('Escape');
  await page.locator('#guide').click();
  await expect(page.locator('#ladder')).toBeVisible();
  await page.locator('#ladder-close').click();
  await expect(page.locator('#ladder')).toBeHidden();
});

test('disagreement marks are on by default, M toggles them, and D swaps to source changes',async({page})=>{
  await open(page); await page.keyboard.press('?');
  // The first toy pair sets a dash list against the same words as prose.
  await expect(page.locator('#marks')).toHaveAttribute('aria-pressed','true');
  await expect(page.locator('#marks-help')).toBeVisible();
  expect(await page.locator('#a-text mark.dis').count()).toBeGreaterThan(0);
  expect(await page.locator('#b-text mark.dis').count()).toBeGreaterThan(0);
  await expect(page.locator('#a-text mark.nl')).toHaveCount(3);
  // Each dash item B lacks gets its own thin bar, including the ones next to a changed stop.
  await expect(page.locator('#b-text mark.gap')).toHaveCount(3);
  // Marks never change the words themselves.
  await expect(page.locator('#a-text')).toHaveJSProperty('textContent',toy[0].a.text);
  await expect(page.locator('#b-text')).toHaveJSProperty('textContent',toy[0].b.text);
  await page.locator('#a-text mark.dis').first().hover();
  expect(await page.locator('#b-text mark.linked').count()).toBeGreaterThan(0);
  await page.keyboard.press('m');
  await expect(page.locator('#candidates mark')).toHaveCount(0);
  await expect(page.locator('#marks')).toHaveAttribute('aria-pressed','false');
  await expect(page.locator('#marks-help')).toBeHidden();
  await page.keyboard.press('m');
  expect(await page.locator('#candidates mark').count()).toBeGreaterThan(0);
  await page.keyboard.press('d');
  await expect(page.locator('#diff')).toHaveAttribute('aria-pressed','true');
  await expect(page.locator('#marks')).toHaveAttribute('aria-pressed','false');
  await expect(page.locator('#candidates mark')).toHaveCount(0);
  expect(await page.locator('.candidate ins').count()).toBeGreaterThan(0);
  expect(await page.locator('.candidate del').count()).toBeGreaterThan(0);
  await expect(page.locator('#diff-help')).toBeVisible();
  await page.keyboard.press('m');
  await expect(page.locator('#diff')).toHaveAttribute('aria-pressed','false');
  await expect(page.locator('.candidate ins')).toHaveCount(0);
  expect(await page.locator('#candidates mark').count()).toBeGreaterThan(0);
  // The comma-only pair marks the comma, and a thin bar on the side without it.
  await page.keyboard.press('s');
  await expect(page.locator('#b-text mark.dis')).toHaveText([',']);
  await expect(page.locator('#a-text mark.gap')).toHaveCount(1);
});

test('the review fits the window at 1100 by 800, with no page scroll, for every paragraph-length pair',async({page})=>{
  await open(page);
  await expectFits(page); // with the guide open
  await page.keyboard.press('?');
  // The pair shaped like a real one (about 420 characters, a list against prose) fits without any inner scroll.
  for (const id of ['source-band','a-text','b-text']) expect(await inside(page,id)).toBe(true);
  await expectFits(page);
  await page.screenshot({path:`${screenshotDir}/list-against-prose.png`});
  for (let i=1;i<4;i++) { await page.keyboard.press('s'); await expect(page.locator('#source')).toHaveText(toy[i].source); await expectFits(page); }
  // The longest toy pair steps the type down; anything left scrolls inside the panes, never the page.
  await expect(page.locator('#workspace')).toHaveAttribute('data-size','2');
  await page.screenshot({path:`${screenshotDir}/long-pair.png`});
  await page.locator('#a-text').evaluate(e => { e.scrollTop=e.scrollHeight; e.dispatchEvent(new Event('scroll')); });
  await expect.poll(() => page.locator('#b-text').evaluate(e => e.scrollTop)).toBeGreaterThan(0);
  await page.keyboard.press('n');
  await expectFits(page);
});

test('the review fits a narrow 390 by 700 window: panes stack and scroll inside, the bar stays pinned',async({browser})=>{
  const context=await browser.newContext({viewport:{width:390,height:700},colorScheme:'light',reducedMotion:'reduce'});
  const page=await context.newPage(); await open(page);
  await expectFits(page);
  await page.keyboard.press('?');
  for (let i=0;i<4;i++) {
    if (i) await page.keyboard.press('s');
    await expect(page.locator('#source')).toHaveText(toy[i].source);
    await expectFits(page);
    const a=(await page.locator('.candidate').first().boundingBox())!, b=(await page.locator('.candidate').last().boundingBox())!;
    expect(b.y).toBeGreaterThan(a.y+a.height-1);
  }
  await page.screenshot({path:`${screenshotDir}/narrow-long.png`});
  await context.close();
});

test('keyboard-only choices, notes, undo, skip, pause, the ledger and the summary',async({page})=>{
  const errors:string[]=[];
  page.on('pageerror',e=>errors.push(e.message));
  const network:string[]=[];
  page.on('request',r=>{if(!r.url().startsWith('http://localhost:1431/')) network.push(r.url());});
  await open(page);
  await expect(page.locator('#progress')).toHaveText(`0 of ${total}`);
  await expect(page.locator('#ledger i')).toHaveCount(total);
  await expect(page.locator('#ledger i.next')).toHaveCount(1);
  await page.keyboard.press('?');
  const original=await page.locator('#source').innerText();
  await page.keyboard.press('n');
  await expect(page.locator('#note')).toBeFocused();
  await page.keyboard.type('a b t w u n s d m ?: preserve the meaning.');
  await expect(page.locator('#progress')).toHaveText(`0 of ${total}`);
  await page.keyboard.press('Escape');
  await expect(page.locator('#note-panel')).toBeHidden();
  expect(await page.evaluate(() => document.activeElement === document.body)).toBe(true);
  await page.keyboard.press('a');
  await expect(page.locator('#progress')).toHaveText(`1 of ${total}`);
  await expect(page.locator('#ledger i.done')).toHaveCount(1);
  await page.keyboard.press('u');
  await expect(page.locator('#progress')).toHaveText(`0 of ${total}`);
  await expect(page.locator('#source')).toHaveText(original);
  await page.keyboard.press('n');
  await expect(page.locator('#note')).toHaveValue('a b t w u n s d m ?: preserve the meaning.');
  await page.keyboard.press('Escape');
  await page.keyboard.press('s');
  await expect(page.locator('#source')).not.toHaveText(original);
  await page.keyboard.press('Escape');
  await expect(page.locator('#paused')).toBeVisible();
  await expect(page.locator('#workspace')).toBeHidden();
  await expect(page.locator('#decision')).toBeHidden();
  await page.keyboard.press('w');
  await expect(page.locator('#progress')).toHaveText(`0 of ${total}`);
  await page.keyboard.press('Escape');
  await expect(page.locator('#workspace')).toBeVisible();
  // Every choice key and arrow alias, plus held-key repeat suppression.
  const keys=['a','ArrowLeft','b','ArrowRight','t','ArrowDown','w'];
  for(let i=0;i<keys.length;i++) { await page.keyboard.press(keys[i]); await expect(page.locator('#progress')).toHaveText(`${i+1} of ${total}`); }
  // Ticks count judgments only; none of them says which side won.
  await expect(page.locator('#ledger i.done')).toHaveCount(7);
  expect(await page.locator('#ledger i').evaluateAll(ticks => [...new Set(ticks.map(t => t.className))].sort())).toEqual(['','done','next']);
  await page.keyboard.down('a');
  await expect(page.locator('#progress')).toHaveText(`8 of ${total}`);
  await page.keyboard.down('a');
  await expect(page.locator('#progress')).toHaveText(`8 of ${total}`);
  await page.keyboard.up('a');
  for(let i=8;i<25;i++){ await page.keyboard.press('t'); await expect(page.locator('#progress')).toHaveText(`${i+1} of ${total}`); }
  await expect(page.locator('#status')).toContainText('short break');
  await expect(page.locator('#notice')).toBeVisible();
  await expect(page.locator('#notice')).toContainText('set of 25');
  for(let i=25;i<total-1;i++){ await page.keyboard.press('t'); await expect(page.locator('#progress')).toHaveText(`${i+1} of ${total}`); }
  await expect(page.locator('#notice')).toBeHidden();
  await expect(page.locator('#source')).toHaveText(original);
  await expect(page.locator('#note-preview')).toContainText('preserve the meaning');
  await page.keyboard.press('a');
  await expect(page.locator('#summary')).toBeVisible();
  await expect(page.locator('#decision')).toBeHidden();
  await expect(page.locator('#counts')).toContainText('A better4');
  await expect(page.locator('#counts')).toContainText('B better2');
  await expect(page.locator('#counts')).toContainText(`Tie${total-7}`);
  await expect(page.locator('#counts')).toContainText('Both wrong1');
  await expect(page.locator('.repeat-note')).toBeVisible();
  await tabTo(page,'export');
  const downloaded=page.waitForEvent('download');
  await page.keyboard.press('Enter');
  const download=await downloaded; expect(download.suggestedFilename()).toBe('summary.json');
  await download.saveAs('verification/browser-summary.json');
  await page.screenshot({path:`${screenshotDir}/summary.png`});
  await page.keyboard.press('u');
  await expect(page.locator('#progress')).toHaveText(`${total-1} of ${total}`);
  await expect(page.locator('#workspace')).toBeVisible();
  expect(errors).toEqual([]); expect(network).toEqual([]);
});

for(const appearance of ['light','dark'] as const) {
  test(`${appearance} appearance, focus and narrow layout`,async({page,browser})=>{
    await page.emulateMedia({colorScheme:appearance,reducedMotion:'reduce'});
    await open(page); await page.keyboard.press('?');
    await page.keyboard.press('Tab');
    const outline=await page.evaluate(()=>getComputedStyle(document.activeElement!).outlineStyle);
    expect(outline).toBe('solid');
    await page.screenshot({path:`${screenshotDir}/${appearance}.png`});
    // A separate page for the narrow check; never resize the main visible tab.
    const context=await browser.newContext({viewport:{width:390,height:844},colorScheme:appearance,reducedMotion:'reduce'});
    const narrow=await context.newPage(); await open(narrow); await narrow.keyboard.press('?');
    await expectFits(narrow);
    const a=await narrow.locator('.candidate').first().boundingBox();
    const b=await narrow.locator('.candidate').last().boundingBox();
    expect(b!.y).toBeGreaterThan(a!.y+a!.height-1);
    await narrow.screenshot({path:`${screenshotDir}/${appearance}-narrow.png`});
    await context.close();
  });
}

test('word differences and disagreement marks remain accurate',async({page})=>{
  await open(page);
  const result=await page.evaluate(async(toyPair)=>{
    // Same-origin module under test; all data is synthetic.
    const {diff,marks}=await import('/src/diff.ts');
    const inspect=(source:string,candidate:string)=>{
      const div=document.createElement('div'); div.append(diff(source,candidate));
      return {inserted:[...div.querySelectorAll('ins')].map(x=>x.textContent).join(''),deleted:[...div.querySelectorAll('del')].map(x=>x.textContent).join('')};
    };
    const pair=(a:string,b:string)=>{
      const [x,y]=marks(a,b).map(f=>{const d=document.createElement('div'); d.append(f); return d;});
      const list=(d:HTMLElement,kind:string)=>[...d.querySelectorAll(`mark.${kind}`)].map(m=>m.textContent);
      return {a:list(x,'dis'),b:list(y,'dis'),gapsA:list(x,'gap').length,gapsB:list(y,'gap').length,nlB:list(y,'nl').length,textA:x.textContent,textB:y.textContent,ops:[...x.querySelectorAll('mark')].map(m=>m.dataset.op)};
    };
    const words=Array.from({length:1100},(_,i)=>`word${i}`); const changed=[...words]; changed[550]='replacement';
    return {simple:inspect('one two three','one four three'),repeated:inspect('go go now','go now'),long:inspect(words.join(' '),changed.join(' ')),markup:inspect('plain','<script>toy</script>'),
      comma:pair('in town and then','in town, and then'),stop:pair('the week. Then','the week: Then'),word:pair('on Thursday afternoon, and','on Thursday morning, and'),
      list:pair('Notes for Saturday. We need help.','Notes for Saturday:\n- We need help.'),same:pair('identical text','identical text'),
      items:pair('Reminder this week. Floor 3 needs covers. Please check the cart, and tell Marguerite.','Reminder this week:\n- Floor 3 needs covers.\n- Please check the cart.\n- And tell Marguerite.'),
      longMarks:pair(words.join(' '),changed.join(' ')),toyPair:pair(toyPair.a.text,toyPair.b.text)};
  },toy[3]);
  expect(result.simple).toEqual({inserted:'four ',deleted:'two '});
  expect(result.repeated.deleted.trim()).toBe('go');
  expect(result.long.inserted.trim()).toBe('replacement');
  expect(result.long.deleted.trim()).toBe('word550');
  expect(result.markup.inserted).toBe('<script>toy</script>');
  expect(result.comma).toMatchObject({a:[],b:[','],gapsA:1,gapsB:0});
  expect(result.stop).toMatchObject({a:['.'],b:[':']});
  expect(result.word).toMatchObject({a:['afternoon,'],b:['morning,']});
  expect(result.list.nlB).toBe(1);
  expect(result.list.b).toContain('-');
  expect(result.list.gapsA).toBe(1);
  // Prose against a dash list: one thin bar per item, and only the changed characters marked.
  expect(result.items).toMatchObject({a:['.',',','a'],gapsA:3,nlB:3});
  expect(result.same).toMatchObject({a:[],b:[],gapsA:0,gapsB:0});
  expect(result.longMarks).toMatchObject({a:['word550'],b:['replacement']});
  expect(result.toyPair.textA).toBe(toy[3].a.text);
  expect(result.toyPair.textB).toBe(toy[3].b.text);
});

// The macOS web view delivers only Escape's keyup, so a keyup alone must close the guide and then pause.
test('Esc works from its keyup alone, as the native window delivers it',async({page})=>{
  await open(page);
  const escUp=() => page.evaluate(() => document.body.dispatchEvent(new KeyboardEvent('keyup',{key:'Escape',bubbles:true})));
  await expect(page.locator('#ladder')).toBeVisible();
  await escUp();
  await expect(page.locator('#ladder')).toBeHidden();
  await escUp();
  await expect(page.locator('#paused')).toBeVisible();
  await escUp();
  await expect(page.locator('#workspace')).toBeVisible();
});

test('time left starts after the first judgment as a range and firms up to one figure',async({page})=>{
  await open(page);
  await page.keyboard.press('?');
  await expect(page.locator('#estimate')).toHaveText('Time estimate after the first pair');
  const span='(\\d+ min|\\d+ h( \\d+ min)?)';
  await page.keyboard.press('t');
  await expect(page.locator('#progress')).toHaveText(`1 of ${total}`);
  await expect(page.locator('#estimate')).toHaveText(new RegExp(`^(\\d+|${span}) to ${span} left$`));
  for (let n=1;n<20;n++) { await page.keyboard.press('t'); await expect(page.locator('#progress')).toHaveText(`${n+1} of ${total}`); }
  await expect(page.locator('#estimate')).toHaveText(new RegExp(`^about ${span} left$`));
});

// A shortcut acts without moving focus, so no keyboard ring appears on a button.
test('shortcuts leave no focus ring behind',async({page})=>{
  await open(page); await page.keyboard.press('?');
  const onBody=() => page.evaluate(() => document.activeElement === document.body);
  await page.keyboard.press('n'); await expect(page.locator('#note')).toBeFocused();
  await page.keyboard.press('Escape'); await expect(page.locator('#note-panel')).toBeHidden();
  expect(await onBody()).toBe(true);
  await page.keyboard.press('Escape'); await expect(page.locator('#paused')).toBeVisible();
  expect(await onBody()).toBe(true);
  await page.keyboard.press('Escape'); await expect(page.locator('#workspace')).toBeVisible();
  expect(await onBody()).toBe(true);
  await page.keyboard.press('t'); await expect(page.locator('#progress')).toHaveText(`1 of ${total}`);
});
