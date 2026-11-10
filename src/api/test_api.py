# %%
import json

import pandas as pd
import requests
import sqlalchemy

con = sqlalchemy.create_engine("sqlite:///../../data/analytics/database.db")

# NaN não é JSON válido: o to_json troca por null e a API converte de volta para NaN
df = pd.read_sql("SELECT * FROM fs_all LIMIT 5", con)
data = json.loads(df.to_json(orient="records"))

# %%
resp = requests.post("http://localhost:5001/predict", json={"data": data[0]})
print(resp.status_code, resp.json())

# %%
resp = requests.post("http://localhost:5001/predict_many", json={"data": data})
print(resp.status_code, resp.json())
# %%
