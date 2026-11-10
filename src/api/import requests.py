# %%
import requests

resp = requests.post("http://localhost:5001/predict")
resp.json
# %%
