# Agri Market Price Trends & Sell Advisory Dashboard — Week 1

## What's in this starter kit
- `generate_mock_data.py` — creates `mandi_prices.csv`, 120 days of daily prices for 8 crops × 6 regions
- `app.py` — the Streamlit dashboard (filters, trend charts, mandi comparison, naive forecast, rule-based advisory, mock news feed, CSV export)
- `requirements.txt` — Python dependencies

## How to run it (on your Ubuntu VM, same setup as your Big Data course)

```bash
cd agri-dashboard
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt --break-system-packages   # or drop the flag inside a venv
python3 generate_mock_data.py     # creates mandi_prices.csv
streamlit run app.py              # opens the dashboard in your browser
```

## Why mock data first?
Your brief flags data freshness/accuracy as a real risk. Real scraping from
pakissan.com or PBS government portals is inconsistent and can eat your whole
Week 1. The standard MVP move: build the dashboard + advisory logic against
realistic **synthetic** data now (with a scripted potato "blight" price spike
so the advisory/news features have something meaningful to react to), then
swap in real or user-uploaded CSV data later — the app code barely changes.

## Crops & regions chosen (fits your brief's "6-8 crops, 4-6 mandis")
- **Crops:** Wheat, Rice, Potato, Tomato, Onion, Sugarcane, Maize, Chili
- **Regions:** Lahore, Faisalabad, Rawalpindi/Islamabad, Multan, Gujranwala, Karachi

## What's already covered vs. what's next

| Brief requirement | Status |
|---|---|
| Filters (crop, region, date range) | ✅ Done |
| Current price + 7/30-day trend charts | ✅ Done |
| Simple forecasting (moving average) | ✅ Done (naive MA projection) |
| Sell advisory | ✅ Rule-based version done — Week 3 upgrades to Gemini prompt |
| Mandi comparison | ✅ Done |
| News/alerts feed | ✅ Mocked with static examples |
| Export reports | ✅ CSV done — PDF export is a Week 3/6 add-on |
| Real/scraped data | ⏳ Week 1-2: source from pakissan.com, PBS, or Kaggle agri datasets, or accept CSV upload |
| Mobile responsive / Flutter view | ⏳ Streamlit is reasonably mobile-friendly by default; revisit in Week 4 |
| Auth / accounts / freemium | ⏳ Week 5 |

## Suggested next steps (rest of Week 1)
1. Run this locally, confirm it works end-to-end.
2. Try swapping in one real data source (even a manually copied CSV from a
   government portal for one crop) to test the "upload CSV" path early.
3. Sketch which 4-6 real stakeholders you'll show this to in Week 4 (the brief
   suggests "students with farmer family" — worth lining up now).
4. Start your daily [Daily Progress] emails to academiasupervisor.qau@gmail.com
   summarizing what you did — easiest if you write a one-line note right after
   each session while it's fresh.
