// Game situation as the umpire would state it between pitches. Validated and frozen so a
// rule predicate can never see an impossible count or out total.
const BASES = ['first','second','third'];

export function makeSituation({inning=1,half='top',outs=0,balls=0,strikes=0,runners=[],score=null,pitcher=null}={}) {
  const int=(v,lo,hi,name)=>{
    if (!Number.isInteger(v) || v<lo || v>hi) throw new RangeError(`${name} must be an integer ${lo}-${hi}, got ${v}`);
    return v;
  };
  if (half!=='top' && half!=='bottom') throw new RangeError(`half must be 'top' or 'bottom', got ${half}`);
  const on=new Set(runners);
  for (const b of on) if (!BASES.includes(b)) throw new RangeError(`unknown base ${b}`);
  if (score!==null) for (const k of ['home','away']) int(score[k],0,999,`score.${k}`);
  if (pitcher!==null) {
    int(pitcher.pitches,0,300,'pitcher.pitches');
    if (pitcher.age!==undefined) int(pitcher.age,4,25,'pitcher.age');
  }
  return Object.freeze({
    inning:int(inning,1,99,'inning'),half,
    outs:int(outs,0,2,'outs'),balls:int(balls,0,3,'balls'),strikes:int(strikes,0,2,'strikes'),
    runners:Object.freeze(Object.fromEntries(BASES.map(b=>[b,on.has(b)]))),
    score:score&&Object.freeze({home:score.home,away:score.away}),
    pitcher:pitcher&&Object.freeze({...pitcher})
  });
}

// Bases where a force play is possible on a ball in play: first (the batter-runner), then the
// next base for each runner in the unbroken chain behind the batter.
export function forcedBases(s) {
  const forced=['first'];
  if (s.runners.first) forced.push('second'); else return forced;
  if (s.runners.second) forced.push('third'); else return forced;
  if (s.runners.third) forced.push('home');
  return forced;
}
