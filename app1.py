
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import ccxt
from streamlit_autorefresh import st_autorefresh
from datetime import datetime
from collections import defaultdict

# --- Config ---
st.set_page_config(layout="wide")
st.title("🚨 Order Book Wall & Trap Monitor (Smart Refresh)")
st_autorefresh(interval=10 * 1000, key="refresh")

# --- Exchange Setup ---
exchange = ccxt.binance()
symbols = exchange.load_markets()
usdt_pairs = sorted([s for s in symbols if s.endswith("/USDT") and symbols[s]['active']])

# --- Session State ---
state = st.session_state
if "prev_bids" not in state: state.prev_bids = None
if "prev_asks" not in state: state.prev_asks = None
if "prev_price" not in state: state.prev_price = None
if "signal_cache" not in state: state.signal_cache = []
if "prev_walls" not in state: state.prev_walls = {'buy': defaultdict(int), 'sell': defaultdict(int)}
if "last_symbol" not in state: state.last_symbol = "DOGE/USDT"
if "tracked_walls" not in state: state.tracked_walls = {'buy': {}, 'sell': {}}  # <-- Persistent huge walls

# --- Symbol Dropdown with Reset Logic ---
symbol = st.selectbox("📊 Select USDT Trading Pair", usdt_pairs, index=usdt_pairs.index(state.last_symbol))
if symbol != state.last_symbol:
    state.prev_bids = None
    state.prev_asks = None
    state.prev_price = None
    state.signal_cache = []
    state.prev_walls = {'buy': defaultdict(int), 'sell': defaultdict(int)}
    state.tracked_walls = {'buy': {}, 'sell': {}}  # Reset tracked walls on symbol change
    state.last_symbol = symbol

# --- Parameters ---
limit = 100
spoof_threshold = 500000

# --- Fetch Data ---
depth = exchange.fetch_order_book(symbol, limit=limit)
ticker = exchange.fetch_ticker(symbol)
current_price = ticker['last']
prev_price = state.prev_price
state.prev_price = current_price

bids = pd.DataFrame(depth['bids'], columns=['price', 'quantity'])
asks = pd.DataFrame(depth['asks'], columns=['price', 'quantity'])
bids['side'] = 'buy'; asks['side'] = 'sell'
bids = bids.sort_values('price', ascending=False)
asks = asks.sort_values('price')
bids['cumulative_quantity'] = bids['quantity'].cumsum()
asks['cumulative_quantity'] = asks['quantity'].cumsum()

# --- Track Huge Walls Persistently ---
def track_walls(df, side):
    updated = []
    tracked = state.tracked_walls[side]
    for _, row in df.iterrows():
        price, qty = float(row['price']), float(row['quantity'])
        if qty > spoof_threshold:
            if price not in tracked or qty > tracked[price]:
                tracked[price] = qty
                updated.append(f"🧱 NEW {'BUY' if side == 'buy' else 'SELL'} WALL at ${price:.4f} – Qty: {int(qty)}")
    # Remove walls that disappeared or shrunk significantly
    for price in list(tracked.keys()):
        match = df[df['price'] == price]
        if match.empty or float(match['quantity'].values[0]) < spoof_threshold * 0.2:
            del tracked[price]
    return updated

# --- Detection Functions ---
def detect_spoof(current, previous, side):
    signals = []
    if previous is None: return signals
    for price in current['price']:
        curr_qty = current[current['price'] == price]['quantity'].values[0]
        prev_match = previous[previous['price'] == price]
        if not prev_match.empty:
            prev_qty = prev_match['quantity'].values[0]
            if prev_qty > spoof_threshold and curr_qty < prev_qty * 0.2:
                signals.append(f"Spoof on {side.upper()} at ${price:.4f} → {int(prev_qty)} → {int(curr_qty)}")
    return signals

def detect_traps(spoofs, prev_price, curr_price):
    traps = []
    for s in spoofs:
        if "BUY" in s and curr_price < prev_price:
            traps.append(f"🚨 Bull Trap: {s}")
        elif "SELL" in s and curr_price > prev_price:
            traps.append(f"🚨 Bear Trap: {s}")
    return traps

def detect_absorption(bids, asks):
    if bids.iloc[0]['quantity'] > spoof_threshold:
        return f"🛡️ Buyer Absorption at ${bids.iloc[0]['price']:.4f}"
    elif asks.iloc[0]['quantity'] > spoof_threshold:
        return f"🛡️ Seller Absorption at ${asks.iloc[0]['price']:.4f}"
    return ""

def detect_executed_walls(current, previous, side):
    executed = []
    curr_walls = {row['price']: row['quantity'] 
                  for _, row in current.iterrows() 
                  if row['quantity'] > spoof_threshold}
    for prev_price, prev_qty in state.prev_walls[side].items():
        curr_qty = curr_walls.get(prev_price, 0)
        if prev_qty > spoof_threshold and curr_qty < prev_qty * 0.2:
            executed.append(f"✅ Executed {side.upper()} Wall at ${prev_price:.4f} (Was {int(prev_qty)}, Now {int(curr_qty)})")
    state.prev_walls[side] = defaultdict(int, curr_walls)
    return executed

# --- Generate Signals ---
spoofs = detect_spoof(bids, state.prev_bids, "buy") + detect_spoof(asks, state.prev_asks, "sell")
traps = detect_traps(spoofs, prev_price, current_price) if prev_price else []
absorption = detect_absorption(bids, asks)
executed_walls = detect_executed_walls(bids, state.prev_bids, 'buy') + detect_executed_walls(asks, state.prev_asks, 'sell')
new_buy_walls = track_walls(bids, 'buy')
new_sell_walls = track_walls(asks, 'sell')

new_signals = spoofs + traps + new_buy_walls + new_sell_walls + executed_walls
if absorption: new_signals.append(absorption)
if new_signals:
    state.signal_cache = new_signals

# --- Visual Summary of Wall Dominance ---
def get_top_wall(walls):
    return max(walls.items(), key=lambda x: x[1]) if walls else ("-", 0)

buy_top_price, buy_top_qty = get_top_wall(state.tracked_walls['buy'])
sell_top_price, sell_top_qty = get_top_wall(state.tracked_walls['sell'])

st.markdown("## 📊 **Current Wall Summary**")
st.markdown(f"🟩 **Buy Wall**: ${buy_top_price} – {int(buy_top_qty):,}")
st.markdown(f"🟥 **Sell Wall**: ${sell_top_price} – {int(sell_top_qty):,}")

if buy_top_qty > sell_top_qty:
    st.success("📈 Dominant Pressure: **BUY SIDE**")
elif sell_top_qty > buy_top_qty:
    st.error("📉 Dominant Pressure: **SELL SIDE**")
else:
    st.info("🔄 Balanced Order Book")

# --- Display Signals ---
st.markdown("## 🔍 **Order Book Signals (Persistent)**")
if state.signal_cache:
    for signal in state.signal_cache:
        if "Trap" in signal:
            st.error(signal)
        elif "Spoof" in signal:
            st.warning("⚠️ " + signal)
        elif "WALL" in signal:
            st.info(signal)
        elif "Absorption" in signal or "Executed" in signal:
            st.success(signal)
else:
    st.info("📡 Waiting for signals...")

# --- Charts ---
fig_bids = go.Figure()
fig_bids.add_trace(go.Scatter(x=bids['price'], y=bids['cumulative_quantity'],
                              mode='lines', name='Cumulative Bids', line=dict(color='green')))
fig_bids.update_layout(title='Cumulative Bid Depth', xaxis_title='Price', yaxis_title='Quantity')

fig_asks = go.Figure()
fig_asks.add_trace(go.Scatter(x=asks['price'], y=asks['cumulative_quantity'],
                              mode='lines', name='Cumulative Asks', line=dict(color='red')))
fig_asks.update_layout(title='Cumulative Ask Depth', xaxis_title='Price', yaxis_title='Quantity')

col1, col2 = st.columns(2)
col1.subheader("📉 Bids")
col1.dataframe(bids, use_container_width=True)
col2.subheader("📈 Asks")
col2.dataframe(asks, use_container_width=True)

col3, col4 = st.columns(2)
col3.plotly_chart(fig_bids, use_container_width=True)
col4.plotly_chart(fig_asks, use_container_width=True)

# --- Save for next refresh ---
state.prev_bids = bids.copy()
state.prev_asks = asks.copy()
