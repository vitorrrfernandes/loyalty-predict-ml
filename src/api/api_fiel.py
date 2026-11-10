
from flask import Flask
import mlflow

mlflow.set_tracking_uri("http://localhost:5000")
versions = mlflow.search_model_versions(filter_string="name='model_fiel'")
last_version = max([int(i.version) for i in versions])
model = mlflow.sklearn.load_model(f"models:///model_fiel/{last_version}")
app = Flask(__name__)

@app.route("/health_check")
def hello_world():
    return {"status":"ok"}


@app.route("/predict", methods=['POST'])
def predict():
    return{}
