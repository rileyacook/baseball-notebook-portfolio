const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('../web/view_model.js');
test('Enter sends, Shift+Enter and IME composition do not', () => {
  assert.equal(vm.sendKey({key:'Enter'}),true);
  assert.equal(vm.sendKey({key:'Enter',shiftKey:true}),false);
  assert.equal(vm.sendKey({key:'Enter',isComposing:true}),false);
});
test('identity choice sends stable ID instead of menu number', () => {
  assert.deepEqual(vm.selectionFor({player_id:'johnr005',label:'Randy Johnson'}),{player_id:'johnr005'});
  assert.deepEqual(vm.selectionFor({team_id:'NYN'}),{team_id:'NYN'});
  assert.throws(()=>vm.selectionFor({number:1}));
});
test('message payload includes revision and original identity selection', () => {
  assert.deepEqual(vm.sendPayload(' What about 2023? ',{turns:[{},{}]},{team_id:'ATL'}),{question:'What about 2023?',expected_turn:2,selection:{team_id:'ATL'}});
  assert.throws(()=>vm.sendPayload('',{turns:[]}));
});
test('chart projection retains order and all cutoff ties including zero', () => {
  const points = Array.from({length:105},(_,i)=>({label:String(i),value:i<3?0:105-i,formatted:String(i)}));
  const rows=vm.chartRows({points});
  assert.equal(rows.length,105);
  assert.deepEqual(rows.map(r=>r.label),points.map(p=>p.label));
  assert.equal(rows[0].value,0);
  assert.equal(rows[0].width,0);
  assert.equal(rows[3].value,102);
});
test('no-results, clarification, unsupported, operational errors differ', () => {
  assert.equal(vm.outcome({status:'supported',presentation:{state:'no_results'}}),'no_results');
  assert.equal(vm.outcome({status:'needs_clarification'}),'needs_clarification');
  assert.equal(vm.outcome({status:'unsupported'}),'unsupported');
  assert.equal(vm.outcome({status:'error'}),'error');
});
test('missing chart evidence never becomes a zero point', () => {
  assert.deepEqual(vm.chartRows({points:[{value:null},{value:NaN},{value:undefined}]}),[]);
});

test('negative values extend left of zero while preserving their sign', () => {
  const rows=vm.chartRows({points:[{value:-2},{value:0},{value:3}]});
  assert.equal(rows[0].value,-2);
  assert.equal(rows[0].start,0);
  assert.equal(rows[0].width,40);
  assert.equal(rows[2].start,40);
  assert.equal(rows[2].width,60);
  assert.equal(rows[1].width,0);
});

test('saved single-result charts are suppressed; comparable outputs remain available', () => {
  assert.equal(vm.hasComparison({points:[{value:.326}]}),false);
  assert.equal(vm.hasComparison({points:[{value:1},{value:null}]}),false);
  assert.equal(vm.hasComparison({points:[{value:0},{value:1}]}),true);
  assert.equal(vm.hasComparison(null),false);
});

test('clarification form uses the specific requested detail and original question', () => {
  const detail = {field:'rate_basis',title:'How should I measure the rate?',label:'Measure the rate per…',placeholder:'Plate appearance, batter faced, or inning',example:'Per plate appearance'};
  const turn = {question:'What was his strikeout rate?',result:{clarification_message:'Please specify the rate denominator.',clarification_detail:detail}};
  const form = vm.clarificationGuidance(turn);
  assert.equal(form.question,turn.question);
  assert.equal(form.label,detail.label);
  assert.equal(form.example,detail.example);
  assert.equal(form.message,turn.result.clarification_message);
});

test('saved generic follow-up prompts explain failed interpretation rather than claiming an unspecified statistic', () => {
  const form = vm.clarificationGuidance({question:'Who did the Braves play in their last 2025 game?',result:{clarification_message:'Please specify the player, statistic, or scope you want to change.'}});
  assert.equal(form.title,'Restate the question');
  assert.equal(form.label,'Full question to answer');
  assert.match(form.message,/could not connect this follow-up/);
  assert.doesNotMatch(form.message,/specify the player, statistic, or scope/);
});
