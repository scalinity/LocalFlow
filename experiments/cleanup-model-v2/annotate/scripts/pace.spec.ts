import { test, expect } from '@playwright/test';
import { duration, sayLeft, timeLeft } from '../src/pace';
const judged=(n:number, seconds:(i:number)=>number, chars=1400) => Array.from({length:n},(_,i)=>({chars,seconds:seconds(i)}));
const left=(n:number, chars=1400) => Array(n).fill(chars) as number[];

test('no estimate before the first judgment or once nothing is left',()=>{
  expect(timeLeft([],left(5))).toBeNull();
  expect(timeLeft(judged(3,()=>40),[])).toBeNull();
});
test('time left scales with what is still to read',()=>{
  const done=judged(20,()=>40);
  expect(timeLeft(done,left(10,3000))!.seconds).toBeGreaterThan(timeLeft(done,left(10,800))!.seconds*1.8);
});
test('recent pairs count more when the pace changes',()=>{
  const slowThenFast=timeLeft(judged(40,i=>i<20?80:30),left(50))!.seconds/50;
  // Nearer the recent 30 seconds a pair than the overall average of 55.
  expect(slowThenFast).toBeLessThan(50);
  expect(slowThenFast).toBeGreaterThan(30);
});
test('a pair left open while away barely moves the estimate',()=>{
  const steady=timeLeft(judged(20,()=>40),left(50))!.seconds;
  const away=timeLeft(judged(20,i=>i===10?3600:40),left(50))!.seconds;
  expect(away/steady).toBeLessThan(1.15);
});
test('the range narrows as judgments accumulate, then reads as one figure',()=>{
  const wobble=(i:number)=>40*(1+0.3*Math.sin(i*1.7));
  const early=timeLeft(judged(2,wobble),left(100))!, later=timeLeft(judged(40,wobble),left(100))!;
  expect(early.high/early.low).toBeGreaterThan(later.high/later.low);
  expect(sayLeft(early)).toMatch(/^\S.* to .* left$/);
  expect(sayLeft({seconds:2400,low:2100,high:3000})).toBe('35 to 50 min left');
  expect(sayLeft({seconds:4200,low:3300,high:5100})).toBe('55 min to 1 h 25 min left');
  expect(sayLeft(later)).toMatch(/^about .* left$/);
});
test('durations read in minutes, then in five-minute steps and hours',()=>{
  expect(duration(30)).toBe('1 min'); expect(duration(600)).toBe('10 min'); expect(duration(1470)).toBe('25 min');
  expect(duration(4500)).toBe('1 h 15 min'); expect(duration(7200)).toBe('2 h');
});
