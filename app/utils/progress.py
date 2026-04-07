def calcular_percentual_planejado_realizado(
    realizado_metrica: float | int,
    meta_metrica: float | int,
    realizado_acoes: float | int,
    meta_acoes: float | int,
) -> float:
    componentes: list[float] = []

    meta_metrica_num = float(meta_metrica or 0)
    meta_acoes_num = float(meta_acoes or 0)

    if meta_metrica_num > 0:
        componentes.append(float(realizado_metrica or 0) / meta_metrica_num)
    if meta_acoes_num > 0:
        componentes.append(float(realizado_acoes or 0) / meta_acoes_num)

    if not componentes:
        return 0.0

    percentual = (sum(componentes) / len(componentes)) * 100
    return min(round(percentual, 1), 100.0)
