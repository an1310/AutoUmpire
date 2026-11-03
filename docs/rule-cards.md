# Rule cards (situation-driven)

**Status:** engine and tests only. No rule card is verified yet, so with default settings only the "force plays" situation card is shown. Not wired into the AR view.

Given the game situation (count, outs, runners, inning, optional pitcher age and pitch count) and the rule code, `cardsFor()` in `src/rules/engine.js` returns the rule cards that apply. It is pure and synchronous, so it can run on the headset between pitches.

```js
import {makeSituation} from './src/rules/state.js';
import {makeGame,cardsFor} from './src/rules/engine.js';
const game=makeGame({code:'little-league',division:'major'});
cardsFor(makeSituation({outs:1,strikes:2,runners:['first','second']}),game);
// -> {shown:[force plays], withheld:[infield fly, uncaught third strike]}   (until verified)
```

## Rules for the cards

- **Our wording, the book's number.** Card text is written here and cites the rule by number. Rulebook text is copyrighted and is not copied into the repo.
- **Fail-closed.** A `rule` card is shown only when it has a rule number, a source URL, the edition, and the date a person checked the card's logic against that edition. Anything less is returned under `withheld`, so the display can say what it is not showing. `showUnverified:true` is for development only.
- **Situation cards** (`kind:'situation'`) follow from the count, outs and runners alone, such as which bases are force plays. They need no rulebook and are always shown.
- **Ruleset per game.** The rule code (and, for Little League, the division) is a required game setting, never a default. A wrong code gives a confidently wrong card.

## Verification checklist

Everything below was written from memory. Each item needs checking against the current edition before `checked` is set.

| Card | Code | Cite (unverified) | What to confirm |
|---|---|---|---|
| Infield fly | NFHS | 2-19 | Rule number; conditions (fewer than 2 outs, runners on 1st and 2nd or bases loaded, not a line drive or bunt) |
| Infield fly | Little League, USSSA, Perfect Game | — | Rule number; any division or age differences |
| Uncaught third strike | NFHS | 8-1-1b | Rule number; first base unoccupied or two outs |
| Uncaught third strike | Little League | — | Which divisions do not use it. The code assumes tee ball, minor and major do not, and intermediate, junior and senior do |
| Uncaught third strike | USSSA, Perfect Game | — | Whether it applies at every age |
| Time play | NFHS | 9-1-1 | Rule number; the three exceptions (force out, batter-runner before first, preceding runner out for missing a base) |
| Time play | Little League, USSSA, Perfect Game | — | Rule number |
| Pitch count | Little League | Regulation VI | Limits by league age (the code has 7–8: 50, 9–10: 75, 11–12: 85, 13–16: 95, 17–18: 105); the "may finish the batter" rule; whether tournament limits differ |

## Known gaps

- **NFHS pitch counts are set by each state association**, not by NFHS. The state is needed before there can be an NFHS pitch-count card.
- USSSA and Perfect Game limits vary by age group and sometimes by event. They may need per-tournament settings, not fixed data.
- Run rules, courtesy runners, re-entry and time limits are not encoded yet.
- Game state is entered by the caller. Getting it in the field (clicker, voice, scoring app, or reading a broadcast scoreboard) is separate work.
