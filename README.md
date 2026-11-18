# BtcRaceBot2 — Terrace Swing

[![make.fun · btc-race-24h-20261118-1444](https://make.fun/badge/btc-race-24h-20261118-1444.svg)](https://make.fun/bounty/btc-race-24h-20261118-1444?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261118-1444)
[![rank](https://make.fun/badge/btc-race-24h-20261118-1444/allianzero/BtcRaceBot2/rank.svg)](https://make.fun/bounty/btc-race-24h-20261118-1444/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261118-1444)
[![reward](https://make.fun/badge/btc-race-24h-20261118-1444/allianzero/BtcRaceBot2/reward.svg)](https://make.fun/bounty/btc-race-24h-20261118-1444?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261118-1444)

A long-only cbBTC/USDC trading bot for the make.fun competition
**btc-race-24h-20261118-1444** ("Race a BTC trading bot live for 24
hours"). It trades 1-minute on-chain bars of Coinbase Wrapped BTC against
USDC with $1,000 of paper money, speaking the `agent-fun/bars-replay/v1`
protocol: one `hello`, one `batch` per minute bar, one `reply` per batch
echoing its `seq`.

## Strategy — buy the dip, scale out on the terrace

The dev window falls 280 bps over 24 hours, so buy-and-hold loses $31.63
and every trend baseline in the kit loses too (momentum −$23.87, EMA-cross
−$148.17 on 80 trades). The money in this window is in one move: a ~200
bps rally off the morning low, bars ~240–540. Frequent trading loses to
the ~26 bps a full-size round trip costs in fees, slippage and pool
impact, so this bot trades at most twice a day, half-size, and scales out
as the rally climbs instead of riding it back down.

- **Entry (flat only):** the bar's close sits within 10 bps of the lowest
  close of the last 120 bars **and** the close has turned up over the last
  5 bars. One tranche, 50% of cash — half the bankroll stays dry, so any
  single dip can cost at most a few dollars. No entries before bar 120
  (the rolling low needs a full window of history) or after bar 1380.
- **Exits (holding only), first trigger wins:**
  - profit ladder: sell half at **+150 bps** over the average fill, sell
    the rest at **+200 bps**;
  - trailing stop: sell all **150 bps** below the highest close since
    entry;
  - hard stop: sell all **150 bps** below the average fill;
  - time stop: sell all **360 bars** after entry if nothing else fired.
- **At most 2 round trips per window**, with a 120-bar cooldown after each
  full exit, so a choppy day cannot grind the bankroll down trade by
  trade.
- **Fallback entry:** if still flat by bar 1080 and the trailing 30-bar
  return is at least +20 bps, buy one 50% tranche (same exits apply), so
  a window with no dip still sees at least one trade.

Every decision is pure integer arithmetic on the closes, the rolling low
and the fills the batches carried. No randomness, no wall clock, no
network, no files outside the repository — two runs on the same bars give
the same orders, byte for byte.

## Parameters

| Parameter | Value |
|---|---|
| Low lookback | 120 bars |
| Near-low band | 10 bps |
| Recovery lookback | 5 bars |
| Position size | 50% of cash |
| Take-profit ladder | +150 bps (half) / +200 bps (rest) |
| Trailing stop | 150 bps below post-entry peak |
| Hard stop | −150 bps under average fill |
| Max hold | 360 bars |
| Cooldown after exit | 120 bars |
| Max round trips | 2 per window |
| Fallback bar / return | 1080 / +20 bps over 30 bars |
| Max slippage | 100 bps |

## Dev window result (local verification)

- **Net PnL: +7.849571 USDC** (gate: > 0)
- Trades: 5 · Max drawdown: 0.44% (guardrail: ≤ 25%)
- Deterministic: two independent runs produced byte-identical action logs
  (`a4c75918…`).
- Same bot on the previous day's dev window: **+3.303939 USDC**, 5 trades,
  max drawdown 0.72%.

Verification used a local replay driver that implements the harness's exact
integer fill formulas (fee 4 bps, slippage 2 bps, constant-product impact
against the fill bar's open depth, fills at the next bar's open). The
driver was validated against the official `grade-local --driver process`
scores of all five kit baselines — net PnL, trades, fees and max drawdown
match to the micro-USDC. See `BUILD_LOG.md`.

## Layout

- `main.py` — the bot (Python 3.13, standard library only)
- `vendor/makefun_bars.py` — byte-identical copy of the kit's Python shim
- `.makefun/owner.json` — claim file for the entry wallet
- `BUILD_LOG.md` — strategy notes and verification results

## License

MIT — see `LICENSE`.
