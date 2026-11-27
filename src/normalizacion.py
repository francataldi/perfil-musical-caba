import unicodedata


def normalizar_texto_para_comparar(texto):
    if texto is None:
        return ""

    texto_descompuesto = unicodedata.normalize("NFD", str(texto))
    texto_sin_acentos = "".join(caracter for caracter in texto_descompuesto if unicodedata.category(caracter) != "Mn")

    return " ".join(texto_sin_acentos.upper().split())
