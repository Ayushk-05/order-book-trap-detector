import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import ccxt
from streamlit_autorefresh import st_autorefresh
from datetime import datetime
from collections import defaultdict   # <-- Added for executed wall tracking

# --- Config ---
st.set_page_config(layout="wide")
st.title("🚨 Order Book Trap Detection – DOGE/USDT (Smart Refresh)")
st_autorefresh(interval=10 * 1000, key="refresh")

# --- Exchange Setup ---
exchange = ccxt.binance()
symbol = 'DOGE/USDT'
limit = 100
spoof_threshold = 500000

# --- Session State ---
state = st.session_state
if "prev_bids" not in state: state.prev_bids = None
if "prev_asks" not in state: state.prev_asks = None
if "prev_price" not in state: state.prev_price = None
if "signal_cache" not in state: state.signal_cache = []
if "prev_walls" not in state:   # <-- Added for executed wall tracking
    state.prev_walls = {'buy': defaultdict(int), 'sell': defaultdict(int)}

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

# --- Spoof Detection ---
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

# --- Wall Detection ---
def detect_walls(df):
    return [f"🧱 {row['side'].upper()} Wall at ${row['price']:.4f} – Qty: {int(row['quantity'])}" 
            for _, row in df.iterrows() if row['quantity'] > spoof_threshold]

# --- Trap Detection ---
def detect_traps(spoofs, prev_price, curr_price):
    traps = []
    for s in spoofs:
        if "BUY" in s and curr_price < prev_price:
            traps.append(f"🚨 Bull Trap: {s}")
        elif "SELL" in s and curr_price > prev_price:
            traps.append(f"🚨 Bear Trap: {s}")
    return traps

# --- Absorption Detection ---
def detect_absorption(bids, asks):
    if bids.iloc[0]['quantity'] > spoof_threshold:
        return f"🛡️ Buyer Absorption at ${bids.iloc[0]['price']:.4f}"
    elif asks.iloc[0]['quantity'] > spoof_threshold:
        return f"🛡️ Seller Absorption at ${asks.iloc[0]['price']:.4f}"
    return ""

# --- Executed Wall Detection (NEW) ---
def detect_executed_walls(current, previous, side):
    executed = []
    # Track current walls
    curr_walls = {row['price']: row['quantity'] 
                 for _, row in current.iterrows() 
                 if row['quantity'] > spoof_threshold}
    # Compare with previous walls
    for prev_price, prev_qty in state.prev_walls[side].items():
        curr_qty = curr_walls.get(prev_price, 0)
        # Consider executed if >80% filled
        if prev_qty > spoof_threshold and curr_qty < prev_qty * 0.2:
            executed.append(
                f"✅ Executed {side.upper()} Wall at ${prev_price:.4f} (Was {int(prev_qty)}, Now {int(curr_qty)})"
            )
    # Update previous walls tracking
    state.prev_walls[side] = defaultdict(int, curr_walls)
    return executed

# --- Generate New Signals ---
spoofs = detect_spoof(bids, state.prev_bids, "buy") + detect_spoof(asks, state.prev_asks, "sell")
walls = detect_walls(pd.concat([bids, asks]))
traps = detect_traps(spoofs, prev_price, current_price) if prev_price else []
absorption = detect_absorption(bids, asks)

# --- Executed Wall Signals (NEW) ---
executed_walls = (
    detect_executed_walls(bids, state.prev_bids, 'buy') +
    detect_executed_walls(asks, state.prev_asks, 'sell')
)

new_signals = spoofs + traps + walls + executed_walls   # <-- Add executed walls to signals
if absorption: new_signals.append(absorption)

# --- Smart Update: Only overwrite if meaningful new signal
if new_signals:
    state.signal_cache = new_signals  # persist only if there's something new

# --- Show Persistent Signal Panel ---
st.markdown("## 🔍 **Manipulation & Trap Signals (Persistent)**")
if state.signal_cache:
    for signal in state.signal_cache:
        if "Trap" in signal:
            st.error(signal)
        elif "Spoof" in signal:
            st.warning("⚠️ " + signal)
        elif "Wall" in signal:
            st.info(signal)
        elif "Absorption" in signal:
            st.success(signal)
        elif "Executed" in signal:    # <-- Display executed walls as success
            st.success(signal)
else:
    st.info("📡 Waiting for meaningful manipulation...")

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
