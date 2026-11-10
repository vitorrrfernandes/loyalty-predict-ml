# %%
# Compara as versões do model_fiel na mesma OOT da ABT atual.
# Só a OOT serve para comparar versões: o treino e o teste de cada uma saíram de ABTs diferentes.

import os

import mlflow
import pandas as pd
import sqlalchemy
from sklearn import metrics

mlflow.set_tracking_uri(os.getenv("MLFLOW_TRACKING_URI", "http://127.0.0.1:5000"))
con = sqlalchemy.create_engine("sqlite:///../../data/analytics/database.db")

# %%
df = pd.read_sql("SELECT * FROM abt_fiel", con)
df_oot = df[df["dtRef"] == df["dtRef"].max()]

print(
    f"OOT: dtRef {df_oot['dtRef'].max()} | {len(df_oot)} clientes | "
    f"Tx. alvo {100 * df_oot['flFiel'].mean():.2f}%"
)

# %%
# a busca de versões não traz os aliases; eles vêm do modelo registrado ({alias: versão})
client = mlflow.MlflowClient()
aliases = client.get_registered_model("model_fiel").aliases

linhas = []
versions = mlflow.search_model_versions(filter_string="name='model_fiel'")
for v in sorted(versions, key=lambda v: int(v.version)):
    model = mlflow.sklearn.load_model(f"models:/model_fiel/{v.version}")
    proba = model.predict_proba(df_oot[model.feature_names_in_])[:, 1]
    linhas.append({
        "versao": int(v.version),
        "alias": ", ".join(a for a, ver in aliases.items() if str(ver) == str(v.version)) or "-",
        "auc_oot": metrics.roc_auc_score(df_oot["flFiel"], proba),
        "acc_oot": metrics.accuracy_score(df_oot["flFiel"], proba >= 0.5),
    })

print(pd.DataFrame(linhas).round(4).to_string(index=False))
# %%
