# Define o ambiente Conda (pasta .conda dentro do projeto)
CONDA_ENV=$(CURDIR)/.conda
PYTHON=$(CONDA_ENV)/bin/python

# Define os diretórios
ENGINEERING_DIR=src/engineering
ANALYTICS_DIR=src/analytics


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


# ETL das features
.PHONY: etl
etl:
	@echo "Executando scripts de feature store..."
	cd $(ANALYTICS_DIR) && $(PYTHON) pipeline_analytics.py


# Predição
.PHONY: predict
predict:
	@echo "Executando script de predição..."
	cd $(ANALYTICS_DIR) && $(PYTHON) predict_fiel.py


# Coleta + ETL (atalho)
.PHONY: run
run: collect etl


# Alvo padrão
.PHONY: all
all: setup collect etl predict
