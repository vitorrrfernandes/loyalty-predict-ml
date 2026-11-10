# %%

import os

import pandas as pd
import sqlalchemy
import mlflow

con = sqlalchemy.create_engine("sqlite:///../../data/analytics/database.db")

mlflow.set_tracking_uri(os.getenv("MLFLOW_TRACKING_URI", "http://127.0.0.1:5000"))

# %%

# usa a versão marcada como "champion": registrar uma versão nova não muda a produção,
# promover é mover o alias no MLflow
client = mlflow.MlflowClient()
version = client.get_model_version_by_alias("model_fiel", "champion").version
model = mlflow.sklearn.load_model(f"models:/model_fiel/{version}")

# %%

data = pd.read_sql("SELECT * FROM fs_all", con)
dt_ref = data["dtRef"].max()

# o modelo foi treinado sem Zumbis (target.sql), então só escora a mesma população
data = data[data["descLifeCycleAtual"] != "05-Zumbi"].copy()

if data.empty:
    raise SystemExit(f"Nenhum cliente ativo para escorar em {dt_ref}.")

predict = model.predict_proba(data[model.feature_names_in_])[:,1]

data["predictFiel"] = predict
data["versaoModelo"] = int(version)

data = data[['dtRef', 'IdCliente', 'predictFiel', 'versaoModelo']]

# %%
# guarda o histórico: apaga só o dtRef que vai ser escorado de novo e acrescenta
with con.connect() as c:
    try:
        c.execute(sqlalchemy.text("DELETE FROM score_fiel WHERE dtRef = :dt_ref"), {"dt_ref": dt_ref})
        c.commit()
    except sqlalchemy.exc.OperationalError:
        pass  # primeira execução: a tabela ainda não existe

data.to_sql("score_fiel", con, index=False, if_exists='append')
print(f"score_fiel: {len(data)} clientes escorados em {dt_ref} com a versão {version} do model_fiel")
# %%
