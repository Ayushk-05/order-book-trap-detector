# 🚨 Order Book Trap Detector – DOGE/USDT (Real-Time)

A real-time crypto manipulation detector built using Python, Streamlit, and Binance order book data.

This tool identifies and visualizes:

- 🟠 **Spoofing Orders** (fake large orders that disappear)
- 🧱 **Fake Buy/Sell Walls**
- 🚨 **Bull & Bear Traps**
- 🛡️ **Absorption Zones**
- 📈 **Live Bid/Ask Depth Charts**

---

## 🚀 Features

- Real-time updates every 10 seconds (`streamlit_autorefresh`)
- Live order book data using `ccxt`
- Smart detection logic for spoofing, traps, executed walls, and absorption
- Interactive cumulative bid/ask charts (Plotly)
- Persistent signal display for cleaner experience

---

## 🛠️ Tech Stack

- Python
- Streamlit
- Plotly
- pandas
- ccxt
- streamlit-autorefresh

---

## ▶️ How to Run

1. **Install dependencies:**

```bash
pip install streamlit pandas plotly ccxt streamlit-autorefresh
streamlit run app1.py
