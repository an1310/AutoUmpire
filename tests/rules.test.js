import test from 'node:test';
import assert from 'node:assert/strict';
import {makeSituation,forcedBases} from '../src/rules/state.js';
import {makeGame,cardsFor,isVerified} from '../src/rules/engine.js';
import {RULESETS} from '../src/rules/rulesets.js';

const all=(sit,game)=>cardsFor(makeSituation(sit),game,{showUnverified:true}).shown;
const ids=(sit,game)=>all(sit,game).map(c=>c.id);
const card=(sit,game,id)=>all(sit,game).find(c=>c.id===id);
const nfhs=makeGame({code:'nfhs'});

test('situation rejects impossible counts, outs and bases',()=>{
  for (const bad of [{outs:3},{balls:4},{strikes:3},{inning:0},{half:'middle'},{runners:['fourth']},{outs:1.5},{pitcher:{pitches:-1}}])
    assert.throws(()=>makeSituation(bad),RangeError,JSON.stringify(bad));
});
test('force plays follow the unbroken chain of runners from first',()=>{
  const f=r=>forcedBases(makeSituation({runners:r}));
  assert.deepEqual(f([]),['first']);
  assert.deepEqual(f(['first']),['first','second']);
  assert.deepEqual(f(['first','second']),['first','second','third']);
  assert.deepEqual(f(['first','second','third']),['first','second','third','home']);
  assert.deepEqual(f(['second','third']),['first']);       // nobody on first: no force beyond the batter
  assert.deepEqual(f(['first','third']),['first','second']);
});
test('infield fly needs fewer than two outs and runners on first and second',()=>{
  const on=(outs,runners)=>ids({outs,runners},nfhs).includes('infield-fly');
  assert.ok(on(0,['first','second']) && on(1,['first','second','third']));
  assert.ok(!on(2,['first','second']));
  for (const r of [['first'],['second','third'],['first','third'],[]]) assert.ok(!on(0,r),r.join());
});
test('uncaught third strike: batter may run only with first open or two outs',()=>{
  const t=(outs,runners)=>card({strikes:2,outs,runners},nfhs,'uncaught-third-strike').text;
  assert.match(t(0,[]),/can run/);
  assert.match(t(2,['first']),/can run/);
  assert.match(t(1,['first']),/out on strike three even if/);
  assert.match(t(0,['second']),/can run/);
  assert.ok(!ids({strikes:1},nfhs).includes('uncaught-third-strike'));
});
test('Little League needs a division, and some divisions have no uncaught-third-strike rule',()=>{
  assert.throws(()=>makeGame({code:'little-league'}),RangeError);
  assert.throws(()=>makeGame({code:'little-league',division:'majors'}),RangeError);
  assert.throws(()=>makeGame({code:'cricket'}),RangeError);
  const k=division=>card({strikes:2},makeGame({code:'little-league',division}),'uncaught-third-strike').text;
  assert.match(k('major'),/whether or not/);
  assert.match(k('junior'),/can run/);
});
test('time play appears with two outs and a runner in scoring position',()=>{
  assert.ok(ids({outs:2,runners:['third']},nfhs).includes('time-play'));
  assert.ok(ids({outs:2,runners:['second']},nfhs).includes('time-play'));
  assert.ok(!ids({outs:1,runners:['third']},nfhs).includes('time-play'));
  assert.ok(!ids({outs:2,runners:['first']},nfhs).includes('time-play'));
});
test('Little League pitch count warns within 10 of the age limit',()=>{
  const g=makeGame({code:'little-league',division:'major'});
  const pc=(age,pitches)=>card({pitcher:{age,pitches}},g,'pitch-count')?.text;
  assert.equal(pc(12,74),undefined);
  assert.match(pc(12,75),/10 pitches left before the limit of 85/);
  assert.match(pc(12,85),/may finish the current batter/);
  assert.match(pc(8,45),/5 pitches left before the limit of 50/);
  assert.equal(pc(6,80),undefined);   // no limit known for this age: no card rather than a guess
});
test('unverified rule cards are withheld by default; situation cards are not',()=>{
  const {shown,withheld}=cardsFor(makeSituation({outs:0,runners:['first','second']}),nfhs);
  assert.deepEqual(shown.map(c=>c.id),['force-plays']);
  assert.ok(withheld.some(c=>c.id==='infield-fly' && !c.verified));
});
test('a rule counts as verified only with rule number, source URL, edition and check date',()=>{
  const base={kind:'rule',cite:'X 1-1',source:{url:'https://example.org/r.pdf',edition:'2026'},checked:'2026-11-03'};
  assert.ok(isVerified(base));
  for (const drop of [{cite:null},{source:null},{source:{url:'https://example.org/r.pdf'}},{checked:null}])
    assert.ok(!isVerified({...base,...drop}),JSON.stringify(drop));
});
test('every rule card in every code is still unverified (flip this test when sources are checked)',()=>{
  for (const [code,rs] of Object.entries(RULESETS))
    for (const r of rs.rules) if (r.kind==='rule') assert.equal(isVerified(r),false,`${code}/${r.id}`);
});
