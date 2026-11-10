
import os

import pandas as pd
from flask import Flask, request
import mlflow

mlflow.set_tracking_uri(os.getenv("MLFLOW_TRACKING_URI", "http://127.0.0.1:5000"))
versions = mlflow.search_model_versions(filter_string="name='model_fiel'")
last_version = max([int(i.version) for i in versions])
model = mlflow.sklearn.load_model(f"models:///model_fiel/{last_version}")
app = Flask(__name__)

# mesmas categóricas do train.py; o resto é convertido para float como no treino
cat_features = ["descLifeCycleAtual", "descLifeCycleD28"]


def prepara_features(df):
    # no JSON, feature vazia chega como null; o astype(float) transforma em NaN
    X = df[model.feature_names_in_].copy()
    num_features = [c for c in X.columns if c not in cat_features]
    X[num_features] = X[num_features].astype(float)
    return X


@app.route("/health_check")
def hello_world():
    return {"status":"ok"}


@app.route("/predict", methods=['POST'])
def predict():
    try:
        data = request.json["data"]
        df = pd.DataFrame([data])
        X = prepara_features(df)
        predict = model.predict_proba(X)[:, 1]
        return {"IdCliente": data["IdCliente"], "score": float(predict[0])}

    except Exception as err:
        app.logger.exception(err)
        return {"erro": str(err)}, 400


@app.route("/predict_many", methods=['POST'])
def predict_many():
    try:
        data = request.json["data"]
        df = pd.DataFrame(data)
        X = prepara_features(df)
        df["score"] = model.predict_proba(X)[:, 1]
        resp = df[["IdCliente", "score"]].to_dict(orient="records")
        return {"result": resp}

    except Exception as err:
        app.logger.exception(err)
        return {"erro": str(err)}, 400
