"""Terrace Swing: a cbBTC/USDC swing bot for make.fun's bars-replay/v1.

Strategy (original): buy the first real dip of the day, scale out on a
profit ladder, and stop trading after two round trips.

- Entry: the close sits within 10 bps of the lowest close of the last 120
  bars and is ticking back up (above its close 5 bars ago). Only after bar
  120, so the rolling low is built on a full window of history. One tranche,
  50% of cash: half the bankroll stays dry, which caps the drawdown of any
  single dip to a few dollars.
- Exits (checked every bar while holding):
    * profit ladder: sell half at +150 bps over the average fill, sell the
      rest at +200 bps;
    * trailing stop: sell all once the close falls 150 bps below the highest
      close since entry;
    * hard stop: sell all at -150 bps under the average fill;
    * time stop: sell all 360 bars after entry if no other exit fired.
- At most 2 round trips per window, with a 120-bar cooldown after each full
  exit, so a choppy day cannot grind the bankroll down trade by trade.
- Fallback: if still flat at bar 1080 and the trailing 30-bar return is at
  least +20 bps, buy one 50% tranche (the same exits apply), so a window
  with no dip still sees at least one trade.
- No entries after bar 1380.

Protocol: agent-fun/bars-replay/v1, one hello, one batch per 1-minute bar,
one reply per batch echoing its seq. Fully deterministic: no wall clock, no
randomness, no network, no files outside the repo. All state is derived
from the bars and the fills the harness reports, so two runs on the same
data produce byte-identical replies.
"""

import os
import sys
from collections import deque

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor"))
import makefun_bars

SYMBOL = "CBBTC"

# --- strategy parameters (all in basis points unless noted) -----------------
LOW_LOOKBACK = 120       # bars of history behind the rolling low
NEAR_LOW_BPS = 10        # entry: close within this of the rolling low
RECOVERY_BARS = 5        # entry: close above its close this many bars ago
MIN_BAR = 120            # no entries before this batch (history warm-up)
LAST_ENTRY_BAR = 1380    # no entries after this batch
TRANCHE_BPS = 5000       # first (only) tranche: 50% of cash
TP1_BPS = 150            # sell half the position here
TP2_BPS = 200            # sell the rest here
TRAIL_BPS = 150          # sell all this far below the post-entry peak
STOP_BPS = 150           # sell all this far below the average fill
MAX_HOLD_BARS = 360      # sell all this many bars after entry
COOLDOWN_BARS = 120      # bars with no entries after a full exit
MAX_ROUNDTRIPS = 2       # at most this many round trips per window
FALLBACK_BAR = 1080      # fallback entry from this batch if still flat
FALLBACK_MOM_BPS = 20    # fallback: trailing 30-bar return at least this
MAX_SLIPPAGE_BPS = 100   # per order, measured from the latest close


class Bot:
    """One run's state. Everything here is a function of the bars and fills."""

    def __init__(self):
        self.closes = []            # closes seen so far (price-scale ints)
        self._low_deque = deque()   # indices of increasing closes (rolling min)
        self.entry_avg = 0          # average fill price of the open position
        self.peak = 0               # highest close since entry
        self.entry_bar = -1         # batch seq at which the buy filled
        self.tp1_done = False       # first profit-ladder step already sold
        self.cooldown_until = -1    # no entries before this batch seq
        self.roundtrips = 0         # completed round trips this window
        self._next_id = 1           # order client-id counter
        self._tp1_ids = set()       # client ids of take-profit-1 sells

    # -- helpers ------------------------------------------------------------
    def _client_id(self):
        cid = "t%d" % self._next_id
        self._next_id += 1
        return cid

    def _rolling_low(self):
        return self.closes[self._low_deque[0]]

    def _note_close(self, close):
        k = len(self.closes)
        while self._low_deque and self.closes[self._low_deque[-1]] >= close:
            self._low_deque.pop()
        self._low_deque.append(k)
        while self._low_deque[0] <= k - LOW_LOOKBACK:
            self._low_deque.popleft()
        self.closes.append(close)

    def _fold_fills(self, state, batch):
        """Update entry tracking from the fills this batch reports."""
        for fill in batch.get("fills", []):
            if fill.get("symbol") != SYMBOL or fill.get("status") != "filled":
                continue
            price = int(fill["price"])
            qty = int(fill["qty"])
            if fill["side"] == "buy":
                holding = state.positions.get(SYMBOL)
                if holding is None or holding.qty == qty:
                    # Fresh entry: the fill opened the position.
                    self.entry_avg = price
                    self.peak = state.close(SYMBOL)
                    self.entry_bar = state.seq
                    self.tp1_done = False
                else:
                    # Averaging in (not used by this strategy, kept general).
                    old_qty = holding.qty - qty
                    self.entry_avg = (
                        self.entry_avg * old_qty + price * qty
                    ) // holding.qty
            else:  # sell
                if fill["client_id"] in self._tp1_ids:
                    self.tp1_done = True
                    self._tp1_ids.discard(fill["client_id"])
                holding = state.positions.get(SYMBOL)
                if holding is None:
                    # Position fully closed: one round trip is done.
                    self.roundtrips += 1
                    self.cooldown_until = state.seq + COOLDOWN_BARS
                    self.entry_avg = 0
                    self.peak = 0
                    self.entry_bar = -1
                    self.tp1_done = False

    # -- decision -----------------------------------------------------------
    def on_batch(self, state, batch):
        if state.warming_up:
            return []
        # A gap bar (no CBBTC bar this minute) carries no new close: fold
        # any fills, but do not append a stale close to the history and do
        # not decide on it.
        if not any(b.get("symbol") == SYMBOL for b in batch.get("bars", [])):
            self._fold_fills(state, batch)
            return []
        close = state.close(SYMBOL)
        if close is None:
            return []
        self._note_close(close)
        self._fold_fills(state, batch)
        seq = state.seq
        holding = state.positions.get(SYMBOL)
        qty = holding.qty if holding else 0

        if qty > 0:
            self.peak = max(self.peak, close)
            gain_bps = (close - self.entry_avg) * 10000 // self.entry_avg
            # Hard stop first: never let one dip cost more than STOP_BPS.
            if gain_bps <= -STOP_BPS:
                return [self._sell_all(qty)]
            # Profit ladder, half at TP1 then the rest at TP2.
            if TP1_BPS and not self.tp1_done and gain_bps >= TP1_BPS:
                half = qty // 2
                if half > 0 and state.value(SYMBOL, half) >= 1_000_000:
                    cid = self._client_id()
                    self._tp1_ids.add(cid)
                    return [{"side": "sell", "client_id": cid, "symbol": SYMBOL,
                             "qty": half, "max_slippage_bps": MAX_SLIPPAGE_BPS}]
            if TP2_BPS and gain_bps >= TP2_BPS:
                return [self._sell_all(qty)]
            # Trailing stop below the post-entry peak.
            if (self.peak - close) * 10000 // self.peak >= TRAIL_BPS:
                return [self._sell_all(qty)]
            # Time stop: a dip that never bounces frees the slot.
            if seq - self.entry_bar >= MAX_HOLD_BARS:
                return [self._sell_all(qty)]
            return []

        # Flat: look for an entry.
        if (seq < MIN_BAR or seq >= LAST_ENTRY_BAR
                or seq < self.cooldown_until
                or self.roundtrips >= MAX_ROUNDTRIPS):
            return []
        near_low = (close - self._rolling_low()) * 10000 // close <= NEAR_LOW_BPS
        recovering = (len(self.closes) > RECOVERY_BARS
                      and close > self.closes[-1 - RECOVERY_BARS])
        if near_low and recovering:
            return [self._buy(state)]
        if seq >= FALLBACK_BAR and len(self.closes) > 30:
            mom30 = (close * 10000 // self.closes[-31]) - 10000
            if mom30 >= FALLBACK_MOM_BPS:
                return [self._buy(state)]
        return []

    def _buy(self, state):
        amount = state.cash * TRANCHE_BPS // 10000
        return {"side": "buy", "client_id": self._client_id(), "symbol": SYMBOL,
                "notional_quote_units": amount,
                "max_slippage_bps": MAX_SLIPPAGE_BPS}

    def _sell_all(self, qty):
        return {"side": "sell", "client_id": self._client_id(), "symbol": SYMBOL,
                "qty": qty, "max_slippage_bps": MAX_SLIPPAGE_BPS}


def main():
    bot = Bot()
    makefun_bars.run(bot.on_batch)


if __name__ == "__main__":
    main()
