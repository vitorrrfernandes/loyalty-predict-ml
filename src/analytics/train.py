# %%
# IMPORTS

import matplotlib.pyplot as plt
import mlflow
import pandas as pd
import sqlalchemy
from feature_engine import encoding, imputation, selection
from sklearn import ensemble, metrics, model_selection, pipeline

# %%
# CONFIGURAÇÃO

mlflow.set_tracking_uri("http://127.0.0.1:5000")
mlflow.set_experiment(experiment_id=1)

con = sqlalchemy.create_engine("sqlite:///../../data/analytics/database.db")

# %%
# LEITURA DOS DADOS

df = pd.read_sql("select * from abt_fiel", con)
df.head()

# %%
# SAMPLE - OOT

df_oot = df[df["dtRef"] == df["dtRef"].max()].reset_index(drop=True)
df_oot

# %%
# SAMPLE - TREINO E TESTE

target = "flFiel"
features = df.columns.tolist()[3:]

df_train_test = df[df["dtRef"] < df["dtRef"].max()].reset_index(drop=True)

X = df_train_test[features]
y = df_train_test[target]

X_train, X_test, y_train, y_test = model_selection.train_test_split(
    X,
    y,
    test_size=0.2,
    random_state=42,
    stratify=y,
)

print(f"Base Treino: {y_train.shape[0]} Unid. | Tx.target{100 * y_train.mean():.2f}%")
print(f"Base Test: {y_test.shape[0]} Unid. | Tx.target{100 * y_test.mean():.2f}%")

# %%
# EXPLORE - MISSING

s_nas = X_train.isna().mean()
s_nas = s_nas[s_nas > 0]
s_nas

# %%
# EXPLORE - BIVARIADA

cat_features = ["descLifeCycleAtual", "descLifeCycleD28"]
num_features = list(set(features) - set(cat_features))

df_train = X_train.copy()
df_train[target] = y_train.copy()
df_train[num_features] = df_train[num_features].astype(float)

bivariada = df_train.groupby(target)[num_features].median().T
bivariada["ratio"] = (bivariada[1] + 0.001) / (bivariada[0] + 0.001)

# remove as features com a mesma mediana nas duas classes
to_remove = bivariada[bivariada["ratio"] == 1].index.tolist()

for i in to_remove:
    features.remove(i)
    num_features.remove(i)

bivariada = df_train.groupby(target)[num_features].median().T
bivariada["ratio"] = (bivariada[1] + 0.001) / (bivariada[0] + 0.001)
bivariada.sort_values(by="ratio", ascending=False)

# %%

df_train.groupby("descLifeCycleAtual")[target].mean()

# %%

df_train.groupby("descLifeCycleD28")[target].mean()

# %%
# MODIFY - DROP

X_train[num_features] = X_train[num_features].astype(float)

drop_features = selection.DropFeatures(to_remove)

# %%
# MODIFY - MISSING

# github2025 pode ter sido removida no DROP (ratio == 1), entao imputa so o que sobrou
fill_0 = [c for c in ["github2025", "python2025"] if c not in to_remove]

imput_0 = imputation.ArbitraryNumberImputer(
    arbitrary_number=0,
    variables=fill_0,
)

imput_new = imputation.CategoricalImputer(
    fill_value="Nao-Usuario",
    variables=["descLifeCycleD28"],
)

imput_1000 = imputation.ArbitraryNumberImputer(
    arbitrary_number=1000,
    variables=[
        "avgIntervaloDiasVida",
        "avgIntervaloDiasD28",
        "qtdDiasUltimaAtividade",
    ],
)

# %%
# MODIFY - ONE HOT ENCODING

onehot = encoding.OneHotEncoder(variables=cat_features)

# %%
# MODEL

model = ensemble.RandomForestClassifier(
    random_state=42,
    n_estimators=400,
    min_samples_leaf=50,
    n_jobs=2,
)
params = {
        "n_estimators": [100,200,400,500,1000],
        "min_samples_leaf": [10,20,30,50,75,100],
    }

grid = model_selection.GridSearchCV(
            model,
            param_grid=params,
            cv=3,
            scoring="roc_auc",
            refit=True,  
            verbose=3,
            n_jobs=8
    )

# %%
# PIPELINE + ASSESS (registrado no MLflow)

with mlflow.start_run() as r: 

    mlflow.sklearn.autolog()


    model_pipeline = pipeline.Pipeline(
            steps=[
                ("Remocao de Features", drop_features),
                ("Imputacao de Zeros", imput_0),
                ("Imputacao de Nao-Usuario", imput_new),
                ("Imputacao de 1000", imput_1000),
                ("OneHot encoding", onehot),
                ("Algoritmo", grid),
            ]
        )
    model_pipeline.fit(X_train, y_train)

    # ASSESS - Treino
    y_pred_train = model_pipeline.predict(X_train)
    y_proba_train = model_pipeline.predict_proba(X_train)

    acc_train = metrics.accuracy_score(y_train, y_pred_train)
    auc_train = metrics.roc_auc_score(y_train, y_proba_train[:, 1])

    print("Acurácia Treino:", acc_train)
    print("AUC Treino:", auc_train)

    # ASSESS - Teste
    y_pred_test = model_pipeline.predict(X_test)
    y_proba_test = model_pipeline.predict_proba(X_test)

    acc_test = metrics.accuracy_score(y_test, y_pred_test)
    auc_test = metrics.roc_auc_score(y_test, y_proba_test[:, 1])

    print("Acurácia Teste:", acc_test)
    print("AUC Teste:", auc_test)

    # ASSESS - OOT
    # usa as mesmas colunas do treino (features perdeu as colunas de to_remove)
    X_oot = df_oot[X_train.columns]
    y_oot = df_oot[target]

    y_pred_oot = model_pipeline.predict(X_oot)
    y_proba_oot = model_pipeline.predict_proba(X_oot)

    acc_oot = metrics.accuracy_score(y_oot, y_pred_oot)
    auc_oot = metrics.roc_auc_score(y_oot, y_proba_oot[:, 1])

    print("Acurácia Oot:", acc_oot)
    print("AUC OOT:", auc_oot)

    # ASSESS - Baseline
    # chutar "nao fiel" para todos e dar a mesma probabilidade (taxa do treino) para todos
    y_pred_baseline = pd.Series([0] * y_test.shape[0])
    y_proba_baseline = pd.Series([y_train.mean()] * y_test.shape[0])

    acc_baseline = metrics.accuracy_score(y_test, y_pred_baseline)
    auc_baseline = metrics.roc_auc_score(y_test, y_proba_baseline)

    print("Acurácia Baseline:", acc_baseline)
    print("AUC Baseline:", auc_baseline)

    mlflow.log_metrics(
        {
            "acc_train": acc_train,
            "auc_train": auc_train,
            "acc_test": acc_test,
            "auc_test": auc_test,
            "acc_oot": acc_oot,
            "auc_oot": auc_oot,
            "acc_baseline": acc_baseline,
            "auc_baseline": auc_baseline,
        }
    )

    # ASSESS - Curva ROC
    roc_train = metrics.roc_curve(y_train, y_proba_train[:, 1])
    roc_test = metrics.roc_curve(y_test, y_proba_test[:, 1])
    roc_oot = metrics.roc_curve(y_oot, y_proba_oot[:, 1])

    plt.figure(dpi=400)
    plt.plot(roc_train[0], roc_train[1])
    plt.plot(roc_test[0], roc_test[1])
    plt.plot(roc_oot[0], roc_oot[1])
    plt.legend(
        [
            f"Treino: {auc_train}",
            f"Teste: {auc_test}",
            f"OOT: {auc_oot:.4f}",
        ]
    )
    plt.plot([0, 1], [0, 1], "--", color="black")
    plt.grid(True)
    plt.title("Curva ROC")
    plt.savefig("curva_roc.png")

    mlflow.log_artifact("curva_roc.png")

# %%
# ASSESS - FEATURE IMPORTANCE

best_model = model_pipeline[-1].best_estimator_

features_names = model_pipeline[:-1].transform(X_train.head(1)).columns.tolist()

feature_importance = pd.Series(
    best_model.feature_importances_,
    index=features_names,
)

feature_importance.sort_values(ascending=False)


# %%
