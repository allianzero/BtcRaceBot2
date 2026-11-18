# BUILD_LOG — BtcRaceBot2 (Terrace Swing)

Competition: btc-race-24h-20261118-1444 — "Race a BTC trading bot live for
24 hours". Prize $250 USDC, free entry. Built 2026-11-18, deadline
2026-11-19 03:44 WIB.

## Strategy

Terrace Swing (original): buy the first real dip of the day at half size,
scale out on a profit ladder, stop after two round trips.

The dev window falls 280 bps over 24h (start $65,083, end $63,261,
per-minute return stdev 6.7 bps), so buy-and-hold loses $31.63 and every
kit baseline loses (momentum −$23.87, rsi-bollinger −$39.92, adx-momentum
−$75.57, ema-cross −$148.17 on 80 trades). The money in this window is one
move: a ~200 bps rally off the morning low, bars ~240–540. A full-size
round trip costs ~26 bps in fees (4 bps), slippage (2 bps) and pool
impact, so the bot trades at most twice, half-size, and sells into
strength instead of riding the rally back down.

- Entry (flat only): close within 10 bps of the lowest close of the last
  120 bars AND close above its close 5 bars ago. One tranche, 50% of cash.
  No entries before bar 120 (rolling low needs full history) or after bar
  1380.
- Exits (first trigger wins): sell half at +150 bps over the average fill,
  sell the rest at +200 bps; trailing stop 150 bps below the post-entry
  peak; hard stop 150 bps below the average fill; time stop 360 bars after
  entry.
- At most 2 round trips per window, 120-bar cooldown after each full exit.
- Fallback: if still flat by bar 1080 and the trailing 30-bar return is at
  least +20 bps, buy one 50% tranche (same exits), so a window with no dip
  still sees at least one trade.
- Max slippage 100 bps per order.

Parameters (few, round, chosen for robustness, not a knife-edge):
LOW_LOOKBACK=120, NEAR_LOW_BPS=10, RECOVERY_BARS=5, MIN_BAR=120,
LAST_ENTRY_BAR=1380, TRANCHE_BPS=5000, TP1_BPS=150, TP2_BPS=200,
TRAIL_BPS=150, STOP_BPS=150, MAX_HOLD_BARS=360, COOLDOWN_BARS=120,
MAX_ROUNDTRIPS=2, FALLBACK_BAR=1080, FALLBACK_MOM_BPS=20,
MAX_SLIPPAGE_BPS=100.

## Why this shape (research trail)

- EMA-cross entries (fast 8–24 / slow 24–96, with momentum and washout
  filters, 288 combinations swept) all lost on both dev windows: by the
  time a 1-minute EMA cross confirms, the move is done, and the trailing
  stop exits late. Best of that family: −$3.08 today.
- Dip-buy + profit-ladder swept over 256 combinations; the winner plateau
  (TP1 120–150, TP2 200, trail 100–150, hold 360–720) stays positive on
  both windows. A stall exit (sell if under water after 120 bars) was
  tested and rejected: it fires on a knife-edge (a 1 bp fill difference
  flips it) and hurt the dev window; the 360-bar time stop does the same
  slot-freeing job more slowly and without the edge.
- Stage-2 scale-in (average down a further 40 bps) was tested and
  rejected: it lost money on the dev window (−$0.92 vs +$2.35 without it).
- 100% tranche size was tested and rejected: it doubles the stall losses
  and turns the dev window negative (−$8.30 at MAX_RT=2); 50% keeps max
  drawdown under 1% on both windows.
- Chosen config is positive on both available windows with the same
  parameters (no per-window tuning): today +$7.85, yesterday +$3.30.

## Verification of the actual bot

A local replay driver (/tmp/replay2.py) was written as a faithful port of
the kit harness (sim/bars/engine.ts): exact bigint constant-product pool
math, fee 4 bps, slippage 2 bps, fills at the next bar's open, decision
checks in the engine's order, flatten at the last close. Validated against
the official `grade-local --driver process` scores of all five kit
baselines — net PnL, trades, fees and max drawdown match to the
micro-USDC:

| baseline | official net PnL | local driver net PnL |
|---|---|---|
| buy-and-hold | −31.633698 | −31.633698 |
| momentum | −23.865251 | −23.865251 |
| ema-cross | −148.174061 | −148.174061 |
| rsi-bollinger | −39.916751 | −39.916751 |
| adx-momentum | −75.566624 | −75.566624 |

The shipped main.py was then run end-to-end twice through that driver
(`python3 -P -s main.py`, as the grader runs it) on the kit's dev bars:

- Run 1: net PnL **+7.849571 USDC**, 5 trades, 0 rejected, fees 0.806622,
  max drawdown 0.44%, action log sha256
  `a4c759181a37dea5ffdcbcacc82f4eac851cca83a27cfb0d919202054e390709`.
- Run 2: identical — same PnL, same trades, same action log sha256.
- Deterministic: byte-identical action logs across both runs.
- Protocol: exactly one reply per batch, each echoing its seq; clean exit,
  no stderr output.
- Trade sequence: buy 50% batch 298, TP1 sell half batch 472, TP2 sell
  rest batch 505, buy 50% batch 631, time-stop sell batch 992.

Robustness check — same bot, same driver, previous day's dev window
(btc-race-24h-20261117-0603, +49 bps, range-bound):

- Net PnL **+3.303939 USDC**, 5 trades, 0 rejected, max drawdown 0.72%.

## Commands run

```
# official baseline scores (validation of the local driver)
cd ~/workspace/makefun/btc-race-24h-20261118-1444-kit
node cli/makefun.mjs grade-local --kit . --bot baselines/buy-and-hold \
  --driver process --json
node cli/makefun.mjs grade-local --kit . --bot baselines/momentum \
  --driver process --json
node cli/makefun.mjs grade-local --kit . --bot baselines/ema-cross \
  --driver process --json
node cli/makefun.mjs grade-local --kit . --bot baselines/rsi-bollinger \
  --driver process --json
node cli/makefun.mjs grade-local --kit . --bot baselines/adx-momentum \
  --driver process --json

# bot verification (twice, for determinism)
cd ~/workspace/makefun/btc-race-24h-20261118-1444
python3 /tmp/replay2.py --bars \
  ~/workspace/makefun/btc-race-24h-20261118-1444-kit/dataset/bars/CBBTC.ndjson.gz \
  --window-start 1794926640000 --cmd "python3 -P -s main.py"
# same command a second time; action_log_sha256 must match

# robustness: previous day's dev window
python3 /tmp/replay2.py --bars \
  ~/workspace/makefun/btc-race-24h-20261117-0603-kit/btc-race-24h-20261117-0603-kit/dataset/bars/CBBTC.ndjson.gz \
  --window-start 1794808980000 --cmd "python3 -P -s main.py"
```

TODO for the lead: create repo allianzero/BtcRaceBot2 (after
2026-11-18T14:44:00Z), push, then submit with the recorded transcripts
before 2026-11-19 03:44 WIB. Do NOT edit README.md after the recording
seals. Do NOT submit from this session.

## Files

- main.py (entrypoint, Python 3.13, stdlib only)
- vendor/makefun_bars.py (byte-identical copy of the kit SDK shim,
  sha256 80452b00d2eb1e9c959e73d41cda6ca726cdbe7bfa4065d48278c22eccd276ff)
- README.md, LICENSE (MIT), .makefun/owner.json
