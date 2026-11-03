// Which rule cards apply to a situation. Pure and synchronous so it can run on the headset
// between pitches. Fail-closed: a rule card without a verified source is withheld (and
// reported as withheld) unless the caller explicitly asks for unverified cards.
import {RULESETS} from './rulesets.js';
import {forcedBases} from './state.js';

export function isVerified(rule) {
  return rule.kind==='situation' ||
    Boolean(rule.cite && rule.source?.url && rule.source?.edition && rule.checked);
}

export function makeGame({code,division}={}) {
  const ruleset=RULESETS[code];
  if (!ruleset) throw new RangeError(`unknown rule code ${code}; expected one of ${Object.keys(RULESETS).join(', ')}`);
  if (ruleset.divisions && !ruleset.divisions.includes(division))
    throw new RangeError(`${ruleset.name} needs a division: ${ruleset.divisions.join(', ')}`);
  return Object.freeze({code,division:division??null,ruleset});
}

export function cardsFor(situation,game,{showUnverified=false}={}) {
  const forced=forcedBases(situation);const shown=[];const withheld=[];
  for (const rule of game.ruleset.rules) {
    if (!rule.when(situation,game)) continue;
    const card={id:rule.id,kind:rule.kind,title:rule.title,text:rule.say(situation,game,forced),
                cite:rule.cite??null,verified:isVerified(rule)};
    (card.verified||showUnverified?shown:withheld).push(card);
  }
  return {shown,withheld};
}
