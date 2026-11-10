# Define o ambiente Conda (pasta .conda dentro do projeto)
CONDA_ENV=$(CURDIR)/.conda
PYTHON=$(CONDA_ENV)/bin/python

# Define os diretórios
ENGINEERING_DIR=src/engineering
ANALYTICS_DIR=src/analytics
API_DIR=src/api


# Configura o ambiente
.PHONY: setup
setup:
	@echo "Criando o ambiente Conda (se necessário)..."
	@test -x $(PYTHON) || conda create -y -p $(CONDA_ENV) python=3.14
	@echo "Instalando dependências..."
	$(PYTHON) -m pip install -r requirements.txt


# Baixa os dados do Kaggle
.PHONY: collect
collect:
	@echo "Executando scripts de engenharia..."
	cd $(ENGINEERING_DIR) && $(PYTHON) get_data.py


# ETL das features (sempre com os dados recém-baixados)
.PHONY: etl
etl: collect
	@echo "Executando scripts de feature store..."
	cd $(ANALYTICS_DIR) && $(PYTHON) pipeline_analytics.py


# Predição (usa a versão "champion" do model_fiel no MLflow)
.PHONY: predict
predict:
	@echo "Executando script de predição..."
	cd $(ANALYTICS_DIR) && $(PYTHON) predict_fiel.py


# ABT de treino (amostra reprodutível de até 2 datas por cliente)
.PHONY: abt
abt:
	@echo "Criando a ABT..."
	cd $(ANALYTICS_DIR) && $(PYTHON) abt.py


# Treino (precisa do MLflow rodando)
.PHONY: train
train:
	@echo "Treinando o modelo..."
	cd $(ANALYTICS_DIR) && $(PYTHON) train.py


# API de inferência na porta 5001 (a 5000 é do MLflow)
.PHONY: api
api:
	@echo "Subindo a API..."
	cd $(API_DIR) && $(PYTHON) -m flask --app api_fiel run --port 5001


# Monitoramento: score de cada dtRef contra o ciclo de vida real em D+28
.PHONY: monitor
monitor:
	@echo "Conferindo os scores que já venceram..."
	cd $(ANALYTICS_DIR) && $(PYTHON) monitoramento.py


# Coleta + ETL (atalho)
.PHONY: run
run: collect etl


# Alvo padrão
.PHONY: all
all: setup collect etl predict
