import { mkdirSync, writeFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
// Paragraph-length pairs come first so the toy session opens at real length.
const paragraphs = [
 // A dash list against the same words as prose.
 ['Notes for the garden club meeting on Saturday. We need three volunteers for the seed swap table, but only people who can stay until noon, since the hall closes early. Please bring your own trowels and gloves, and let Odile know if the compost bins behind the shed are still full, because the council cannot collect new deliveries until they have been emptied and rinsed out properly, which usually takes most of a morning.',
  'Notes for the garden club meeting on Saturday:\n- We need three volunteers for the seed swap table, but only people who can stay until noon, since the hall closes early.\n- Please bring your own trowels and gloves.\n- And let Odile know if the compost bins behind the shed are still full, because the council cannot collect new deliveries until they have been emptied and rinsed out properly, which usually takes most of a morning.',
  'Notes for the garden club meeting on Saturday. We need three volunteers for the seed swap table, but only people who can stay until noon, since the hall closes early. Please bring your own trowels and gloves, and let Odile know if the compost bins behind the shed are still full, because the council cannot collect new deliveries until they have been emptied and rinsed out properly, which usually takes most of a morning.'],
 // One comma apart.
 ['so the plan is we leave at seven pick up the rental van in town and then drive straight to the lake house without stopping unless someone needs a break. bring snacks for the drive and a warm jacket because it gets cold by the water after sunset and the cabin heater takes a while to get going',
  'So the plan is we leave at seven, pick up the rental van in town and then drive straight to the lake house without stopping, unless someone needs a break. Bring snacks for the drive and a warm jacket, because it gets cold by the water after sunset and the cabin heater takes a while to get going.',
  'So the plan is we leave at seven, pick up the rental van in town, and then drive straight to the lake house without stopping, unless someone needs a break. Bring snacks for the drive and a warm jacket, because it gets cold by the water after sunset and the cabin heater takes a while to get going.'],
 // One word apart, and the word changes a fact.
 ['please move the dentist appointment from tuesday to thursday afternoon and tell the office that the insurance card is the new one with the blue logo not the old green one. if thursday does not work any day next week is fine as long as it is after three because of school pickup',
  'Please move the dentist appointment from Tuesday to Thursday afternoon, and tell the office that the insurance card is the new one with the blue logo, not the old green one. If Thursday does not work, any day next week is fine as long as it is after three, because of school pickup.',
  'Please move the dentist appointment from Tuesday to Thursday morning, and tell the office that the insurance card is the new one with the blue logo, not the old green one. If Thursday does not work, any day next week is fine as long as it is after three, because of school pickup.'],
 // Long, with a self-correction one side leaves unresolved.
 ['okay quick update on the kitchen renovation for everyone on the thread. the cabinets arrived yesterday but two of the upper doors are the wrong shade so I sent photos to the supplier and they promised replacements within ten days. the electrician finished the under cabinet lighting and the new outlets by the window although the one next to the fridge still trips the breaker when the kettle and the toaster run together so please avoid using both at once until he comes back. the countertop template appointment is on tuesday no wait wednesday at two and someone needs to be home to let them in, I can be there until three. the plumber says the sink can go in the same day as the countertop if the template goes well otherwise it moves to the following monday. for the backsplash we narrowed it down to the white zellige tiles or the pale green ones and I would like everyone to vote by friday so I can place the order before the price change. also the old dishwasher is in the garage and the recycling center only takes appliances on the first saturday of the month so it will sit there for a couple of weeks. the painter can start the week after the countertop goes in but he needs the trim color by thursday at the latest so please send me your vote for the soft white or the warm gray before then. finally the budget is still about eight percent over mostly because of the extra lighting so let\'s hold off on the new bar stools for now',
  'Okay, quick update on the kitchen renovation for everyone on the thread. The cabinets arrived yesterday, but two of the upper doors are the wrong shade, so I sent photos to the supplier and they promised replacements within ten days. The electrician finished the under-cabinet lighting and the new outlets by the window, although the one next to the fridge still trips the breaker when the kettle and the toaster run together, so please avoid using both at once until he comes back. The countertop template appointment is on Wednesday at two, and someone needs to be home to let them in; I can be there until three. The plumber says the sink can go in the same day as the countertop if the template goes well; otherwise it moves to the following Monday. For the backsplash, we narrowed it down to the white zellige tiles or the pale green ones, and I would like everyone to vote by Friday so I can place the order before the price change. Also, the old dishwasher is in the garage, and the recycling center only takes appliances on the first Saturday of the month, so it will sit there for a couple of weeks. The painter can start the week after the countertop goes in, but he needs the trim color by Thursday at the latest, so please send me your vote for the soft white or the warm gray before then. Finally, the budget is still about eight percent over, mostly because of the extra lighting, so let’s hold off on the new bar stools for now.',
  'Okay, quick update on the kitchen renovation for everyone on the thread. The cabinets arrived yesterday, but two of the upper doors are the wrong shade, so I sent photos to the supplier and they promised replacements within ten days. The electrician finished the under cabinet lighting and the new outlets by the window, although the one next to the fridge still trips the breaker when the kettle and the toaster run together, so please avoid using both at once until he comes back. The countertop template appointment is on Tuesday, no wait, Wednesday at two, and someone needs to be home to let them in; I can be there until three. The plumber says the sink can go in the same day as the countertop if the template goes well; otherwise it moves to the following Monday. For the backsplash, we narrowed it down to the white zellige tiles or the pale green ones, and I would like everyone to vote by Friday so I can place the order before the price change. Also, the old dishwasher is in the garage, and the recycling center only takes appliances on the first Saturday of the month, so it will sit there for a couple of weeks. The painter can start the week after the countertop goes in, but he needs the trim color by Thursday at the latest, so please send me your vote for the soft white or the warm gray before then. Finally, the budget is still about 8% over, mostly because of the extra lighting, so let’s hold off on the new bar stools for now.']
];
const examples = [
 ['um can you send the notes after lunch please', 'Can you send the notes after lunch, please?', 'Please send the notes before lunch.'],
 ['the blue notebook is on the kitchen table', 'The blue notebook is on the kitchen table.', 'The notebook is blue and on the kitchen table.'],
 ['lets meet on thursday no sorry friday at ten', 'Let’s meet on Friday at ten.', 'Let’s meet on Thursday at ten.'],
 ['add oat milk apples and rice to the list', 'Add oat milk, apples, and rice to the list.', 'Add oat milk, apples, and rice to the list.'],
 ['i finished the draft but i havent sent it yet', 'I finished and sent the draft.', 'I finished the draft, but I haven’t sent it yet.'],
 ['remind me to water the basil tomorrow morning', 'Water the basil tonight.', 'Water the roses tomorrow morning.'],
 ['open the quick note folder and save this there', 'Open the QuickNote folder and save this there.', 'Open the quick note folder and save this there.'],
 ['the walk took about twenty minutes maybe twenty five', 'The walk took about twenty to twenty-five minutes.', 'The walk took exactly twenty-five minutes.'],
 ['thanks for checking i will call when i get home', 'Thanks for checking. I’ll call when I get home.', 'Thanks for checking; I’ll call when I get home.']
];
export function generatePairs() {
 const id = n => `toy-${String(n).padStart(3,'0')}`;
 const pairs = paragraphs.map(([source,a,b],i) => ({pair_id:id(i+1),case_id:`case-${i+1}`,source,a:{text:a},b:{text:b},vocabulary:[]}));
 const contexts = ['', 'this is for the weekend', 'this is for the morning', 'this is for the afternoon'];
 for (let i=0;i<36;i++) {
   const [spoken,a,b]=examples[i%examples.length];
   const context=contexts[Math.floor(i/examples.length)];
   const source=context ? `${spoken} ${context}` : spoken;
   const suffix=context ? ` ${context[0].toUpperCase()}${context.slice(1)}.` : '';
   const n=pairs.length+1;
   pairs.push({pair_id:id(n),case_id:`case-${n}`,source,a:{text:(i%2 ? b:a)+suffix},b:{text:(i%2 ? a:b)+suffix},vocabulary:i%9===6 ? [['quick note','QuickNote']] : []});
 }
 // Four exact content repeats of short pairs, each with a separate pair ID for independent judgment.
 const short=paragraphs.length;
 for (let i=0;i<4;i++) pairs.push({...pairs[short+i],pair_id:id(pairs.length+1)});
 return pairs;
}
const pairs=generatePairs();
const output=resolve(process.argv[2] ?? 'verification/mock/pairs.jsonl');
mkdirSync(dirname(output),{recursive:true});
writeFileSync(output,pairs.map(p => JSON.stringify(p)).join('\n')+'\n',{flag:'wx'});
writeFileSync(new URL('../src/mock-pairs.json',import.meta.url),JSON.stringify(pairs,null,2)+'\n');
console.log(`Generated ${pairs.length} toy pairs, including four repeated pairs.`);
