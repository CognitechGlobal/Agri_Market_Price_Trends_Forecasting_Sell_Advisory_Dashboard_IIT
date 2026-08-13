import pandas as pd

df = pd.read_csv("real_mandi_prices.csv", parse_dates=["Date"])
print("Total unique crops:", df["Crop"].nunique())

sub = df[(df["Crop"] == "Masoor Whole(local)") & (df["City"] == "Faisalabad")].sort_values("Date")
print(f"\nRows for Masoor Whole(local) in Faisalabad: {len(sub)}")
print(sub.tail(15).to_string(index=False))

print(f"\nUnique price values for this combo: {sub['Price'].nunique()}")
print(f"Date range: {sub['Date'].min()} to {sub['Date'].max()}")
