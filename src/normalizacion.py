"""
Normalización de texto para comparar nombres entre fuentes.

Los nombres de barrios, venues y artistas llegan escritos de formas distintas
según la fuente: con y sin tildes, en mayúsculas o minúsculas, con espacios
sobrantes. Comparar con == pierde coincidencias en silencio, que es la peor
forma de perderlas: nada falla, simplemente hay menos datos de los que debería.

Este módulo es importable y no tiene efectos secundarios.
"""

import unicodedata


def normalizar_texto_para_comparar(texto):
    """
    Deja un texto en una forma canónica: mayúsculas, sin tildes, sin espacios
    sobrantes ni repetidos.

    Objetivo
    --------
    Poder comparar strings provenientes de fuentes distintas sin que la
    comparación falle por diferencias de escritura que no cambian el
    significado. "Núñez", "NUÑEZ" y "  nunez " tienen que colapsar al mismo
    valor.

    Cómo funciona la eliminación de tildes
    --------------------------------------
    La normalización Unicode NFD descompone cada carácter acentuado en dos
    puntos de código: la letra base y el acento por separado ("ñ" pasa a ser
    "n" + tilde). Después se descartan los caracteres de categoría Mn
    (mark, nonspacing), que son exactamente esos acentos sueltos.

    Inputs
    ------
    texto : str o cualquier objeto convertible a str.
        Los valores nulos se convierten al string vacío.

    Devuelve
    --------
    str normalizado. Cadena vacía si la entrada era nula.
    """
    if texto is None:
        return ""

    texto_descompuesto = unicodedata.normalize("NFD", str(texto))
    texto_sin_acentos = "".join(
        caracter
        for caracter in texto_descompuesto
        if unicodedata.category(caracter) != "Mn"
    )

    # split() sin argumentos parte por cualquier cantidad de espacios en blanco
    # y descarta los vacíos, así que " LA  BOCA " queda "LA BOCA".
    return " ".join(texto_sin_acentos.upper().split())
