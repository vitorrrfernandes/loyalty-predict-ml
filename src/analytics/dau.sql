SELECT COUNT( DISTINCT idCliente) AS DAU , substr(DtCriacao,1,10) AS DtDia FROM transacoes 
GROUP BY substr(DtCriacao,1,10)
ORDER BY COUNT(DISTINCT idCliente) DESC
