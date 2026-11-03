// Rule cards per rule code. Text is our own wording, never the rulebook's (the books are
// copyrighted); each card points to the rule by number.
//
// A card is shown only once it is VERIFIED: rule number, source URL, edition and the date a
// person checked the logic against that edition. Everything below was written from memory and
// is unverified until then (basis: 'memory'), so the engine withholds it by default.
//
// kind 'situation' cards are pure consequences of the count, outs and runners (which bases are
// force plays); they need no rulebook and are always shown.

const UNCHECKED={source:null,checked:null,basis:'memory'};

const BASE_NAMES={first:'1st',second:'2nd',third:'3rd',home:'home'};
const occupied=s=>['first','second','third'].filter(b=>s.runners[b]);

function infieldFly(cite) {
  return {
    id:'infield-fly',kind:'rule',title:'Infield fly in effect',cite,...UNCHECKED,
    when:s=>s.outs<2 && s.runners.first && s.runners.second,
    say:s=>`Fewer than two outs with runners on ${occupied(s).map(b=>BASE_NAMES[b]).join(', ')}: a fair fly (not a line drive or attempted bunt) an infielder can catch with ordinary effort is an infield fly. Batter is out; runners may advance at their own risk.`
  };
}

function uncaughtThirdStrike(cite,{inEffect=()=>true}={}) {
  return {
    id:'uncaught-third-strike',kind:'rule',title:'Uncaught third strike',cite,...UNCHECKED,
    when:s=>s.strikes===2,
    say:(s,game)=>{
      if (!inEffect(game)) return 'Two strikes: in this division the batter is out on strike three whether or not the catcher holds it.';
      return (!s.runners.first || s.outs===2)
        ? 'Two strikes: if strike three is not caught, the batter can run to first.'
        : 'Two strikes: first base is occupied with fewer than two outs, so the batter is out on strike three even if it is not caught.';
    }
  };
}

function timePlay(cite) {
  return {
    id:'time-play',kind:'rule',title:'Time play: watch the plate',cite,...UNCHECKED,
    when:s=>s.outs===2 && (s.runners.second || s.runners.third),
    say:()=>'Two outs: a run counts only if it scores before the third out, and never when the third out is a force out, the batter-runner put out before reaching first, or a preceding runner put out for missing a base.'
  };
}

// Little League regular-season pitch limits by league age, and the rule that a pitcher who
// reaches the limit mid at-bat may finish that batter.
const LL_PITCH_LIMIT=[[[17,18],105],[[13,16],95],[[11,12],85],[[9,10],75],[[7,8],50]];
function littleLeaguePitchCount(cite) {
  const limit=age=>LL_PITCH_LIMIT.find(([[lo,hi]])=>age>=lo&&age<=hi)?.[1];
  return {
    id:'pitch-count',kind:'rule',title:'Pitch count',cite,...UNCHECKED,
    when:s=>s.pitcher?.age!==undefined && limit(s.pitcher.age)!==undefined && s.pitcher.pitches>=limit(s.pitcher.age)-10,
    say:s=>{
      const L=limit(s.pitcher.age),left=L-s.pitcher.pitches;
      return left>0
        ? `${left} pitches left before the limit of ${L} for a ${s.pitcher.age}-year-old.`
        : `Limit of ${L} reached: the pitcher may finish the current batter, then must be removed.`;
    }
  };
}

function forcePlays() {
  return {
    id:'force-plays',kind:'situation',title:'Force plays',
    when:s=>occupied(s).length>0,
    say:(s,_,forced)=>`Force at ${forced.map(b=>BASE_NAMES[b]).join(', ')}.`
  };
}

// Little League divisions that do not use the uncaught-third-strike rule (from memory: verify).
const LL_NO_UNCAUGHT_K=new Set(['tee-ball','minor','major']);
const LL_DIVISIONS=['tee-ball','minor','major','intermediate','junior','senior'];

export const RULESETS=Object.freeze({
  nfhs:{name:'NFHS (high school)',rules:[forcePlays(),infieldFly('NFHS 2-19'),uncaughtThirdStrike('NFHS 8-1-1b'),timePlay('NFHS 9-1-1')]},
  'little-league':{name:'Little League',divisions:LL_DIVISIONS,rules:[
    forcePlays(),infieldFly(null),
    uncaughtThirdStrike(null,{inEffect:g=>!LL_NO_UNCAUGHT_K.has(g.division)}),
    timePlay(null),littleLeaguePitchCount('Little League Regulation VI')]},
  usssa:{name:'USSSA',rules:[forcePlays(),infieldFly(null),uncaughtThirdStrike(null),timePlay(null)]},
  pg:{name:'Perfect Game',rules:[forcePlays(),infieldFly(null),uncaughtThirdStrike(null),timePlay(null)]}
});
