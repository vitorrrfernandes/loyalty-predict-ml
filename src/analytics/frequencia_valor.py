# %%

import pandas as pd
import sqlalchemy

import seaborn as sns

import matplotlib.pyplot as plt
# %%

from pathlib import Path

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR.parents[1] / "data"

engine = sqlalchemy.create_engine(f"sqlite:///{DATA_DIR / 'loyalty-system' / 'database.db'}")
# %%

def import_query(path):
    with open(path) as open_file:
        return open_file.read()

query = import_query(BASE_DIR / "frequencia_valor.sql")
# %%
df = pd.read_sql(query, engine)
df.head()

df = df[df["qtdePontos"] < 4000]
# %%
plt.plot(df['freq'], df['qtdePontos'], 'o')
plt.grid(True)
plt.xlabel("Freq")
plt.ylabel("Valor")
plt.show()
# %%

from sklearn import cluster

from sklearn import preprocessing

minmax = preprocessing.MinMaxScaler()

X = minmax.fit_transform(df[['freq', 'qtdePontos']])
# %%
kmean = cluster.KMeans(n_clusters=5, random_state=42, max_iter=1000)

kmean.fit(X)

df['cluster_calc'] = kmean.labels_

df.groupby('cluster_calc')['cluster'].count()
# %%
sns.scatterplot(
    data=df,
    x="freq",
    y="qtdePontos",
    hue="cluster",
    palette="deep"
)

plt.hlines(y=1500, xmin=0, xmax=25, colors='black')
plt.hlines(y=750, xmin=0, xmax=25, colors='black')

plt.vlines(x=4, ymin=0, ymax=750, colors='black')
plt.vlines(x=10, ymin=0, ymax=3000, colors='black')
plt.grid()

# %%
# clusters do KMeans com as mesmas linhas de corte, para comparar com a regra do SQL

plt.figure()
sns.scatterplot(
    data=df,
    x="freq",
    y="qtdePontos",
    hue="cluster_calc",
    palette="deep"
)

plt.hlines(y=1500, xmin=0, xmax=25, colors='black')
plt.hlines(y=750, xmin=0, xmax=25, colors='black')

plt.vlines(x=4, ymin=0, ymax=750, colors='black')
plt.vlines(x=10, ymin=0, ymax=3000, colors='black')
plt.grid()

# %%
