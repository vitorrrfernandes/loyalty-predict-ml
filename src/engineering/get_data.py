# %%

import dotenv

dotenv.load_dotenv('../.env')

from kaggle import api

# %%

datasets = [
    'teocalvo/teomewhy-loyalty-system',
    'teocalvo/teomewhy-education-platform',
]


for d in datasets:
    dataset_name = d.split('teomewhy-')[-1]
    print(dataset_name)
    path = f'../../data/{dataset_name}'
    # se o Kaggle compactar o arquivo, ele chega como database.db.zip; o unzip=True extrai
    api.dataset_download_file(d, 'database.db', path=path, unzip=True)
# %%
