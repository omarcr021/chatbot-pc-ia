"""Utilidades compartidas por los scripts del pipeline."""

import sys
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

RAIZ = Path(__file__).resolve().parent
DATA = RAIZ / "data"

USER_AGENT = "ChatbotAcademicoBot/1.0 (script academico de un curso; uso no comercial)"
TIMEOUT_MS = 45_000


def consola_utf8():
    """Evita errores con tildes y eñes en la consola de Windows."""
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


class Robots:
    """Consulta robots.txt con el mismo User-Agent que usa el navegador.

    Si no hay robots.txt (404/410) se permite el acceso, como indica el estándar.
    Si existe pero no se puede leer (403, 5xx, error de red) se bloquea por prudencia.
    """

    def __init__(self):
        self._por_origen = {}

    def _parser(self, url):
        partes = urlsplit(url)
        origen = f"{partes.scheme}://{partes.netloc}"
        if origen not in self._por_origen:
            self._por_origen[origen] = self._descargar(origen)
        return self._por_origen[origen]

    @staticmethod
    def _descargar(origen):
        peticion = urllib.request.Request(
            f"{origen}/robots.txt", headers={"User-Agent": USER_AGENT}
        )
        parser = RobotFileParser()
        try:
            with urllib.request.urlopen(peticion, timeout=30) as respuesta:
                texto = respuesta.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as error:
            if error.code in (404, 410):
                parser.parse([])
                return parser
            print(f"AVISO: robots.txt de {origen} respondió {error.code}; se bloquea.")
            return None
        except OSError as error:
            print(f"AVISO: no se pudo leer robots.txt de {origen} ({error}); se bloquea.")
            return None
        parser.parse(texto.splitlines())
        return parser

    def permitido(self, url):
        parser = self._parser(url)
        return parser is not None and parser.can_fetch(USER_AGENT, url)

    def crawl_delay(self, url):
        """Pausa en segundos pedida por el sitio, o 0 si no pide ninguna."""
        parser = self._parser(url)
        return (parser.crawl_delay(USER_AGENT) or 0) if parser else 0
