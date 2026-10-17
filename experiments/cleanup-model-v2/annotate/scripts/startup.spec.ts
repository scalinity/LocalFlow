import {test,expect} from '@playwright/test';
test('missing input offers explicit memory-only practice and retry',async({page})=>{
 await page.addInitScript(()=>{ (window as any).__TAURI_INTERNALS__={invoke:async()=>{throw 'PAIRS_MISSING';}}; });
 await page.goto('/');
 await expect(page.locator('#failure-title')).toHaveText('Waiting for review pairs.');
 await expect(page.locator('#session-line')).toBeHidden();
 await expect(page.locator('#pause')).toBeHidden();
 await expect(page.locator('#retry')).toBeFocused();
 await page.keyboard.press('Enter');
 await expect(page.locator('#failure-title')).toHaveText('Waiting for review pairs.');
 await page.keyboard.press('Tab'); await expect(page.locator('#try-toy')).toBeFocused();
 await page.screenshot({path:'verification/screenshots/waiting.png',fullPage:true});
 await page.keyboard.press('Enter');
 await expect(page.locator('#mode')).toHaveText('Toy session');
 await expect(page.locator('#progress')).toHaveText('0 of 44');
 await page.keyboard.press('a'); await expect(page.locator('#progress')).toHaveText('1 of 44');
 await expect(page.locator('#save-label')).toHaveText('Toy data, kept in memory only');
 await page.locator('#real-session').click();
 await expect(page.locator('#failure-title')).toHaveText('Waiting for review pairs.');
 await expect(page.locator('body')).not.toContainText('/Users/');
});
test('other startup errors do not masquerade as missing input or leak paths',async({page})=>{
 await page.addInitScript(()=>{(window as any).__TAURI_INTERNALS__={invoke:async()=>{throw '/private/data/unknown-error';}};});
 await page.goto('/');
 await expect(page.locator('#failure-title')).toHaveText('Couldn’t open this session.');
 await expect(page.locator('#try-toy')).toBeHidden();
 await expect(page.locator('#session-line')).toBeHidden();
 await expect(page.locator('body')).not.toContainText('/private/');
});
