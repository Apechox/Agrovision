"""
SERVIDOR HTTP LOCAL DE AGROVISION (solo librería estándar, sin dependencias nuevas)

    python -m web.server            # http://127.0.0.1:8000
    python -m web.server --puerto 8080

Rutas:
    GET  /                       página (web/static/index.html)
    GET  /video?vista=...        video MJPEG: detecciones | mascara | limpia
    GET  /api/estado             estado, observaciones, registro e incidencias (JSON)
    GET  /api/dashboard          conteos para las gráficas (JSON)
    GET  /api/registro.csv       CSV de toda la cola; ?formato=excel (por defecto) | datos
    (cada POST /api/fuente/archivo agrega un archivo a la cola)
    GET  /api/vista.png          descarga la última vista anotada
    POST /api/fuente/archivo     cuerpo = archivo crudo; ?nombre=video.mp4
    POST /api/fuente/camara      ?n=0
    POST /api/fuente/muestra     usa la foto de ejemplo del dataset
    POST /api/hsv                cuerpo JSON {"min":[h,s,v],"max":[h,s,v]}
    POST /api/roi                cuerpo JSON {"x":..,"y":..,"w":..,"h":..} (zona de medición, px)
                                 o {"completa": true} para volver al cuadro completo
    POST /api/cola/quitar?i=     quita el archivo i de la cola | /api/cola/vaciar vacía la cola
    POST /api/cola/mover?de=&a=  cambia el orden de análisis (solo archivos en espera)    POST /api/iniciar | /api/detener | /api/repetir

Seguridad: escucha SOLO en 127.0.0.1 y rechaza peticiones con cabecera Origin ajena
(evita que otra página abierta en tu navegador dispare acciones sobre la cámara).
"""

import argparse
import json
import mimetypes
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import cv2
import numpy as np

from web.motor import Motor

ESTATICOS = Path(__file__).resolve().parent / "static"
MAX_SUBIDA = 500 * 1024 * 1024  # 500 MB
ERRORES_CLIENTE = (BrokenPipeError, ConnectionResetError, ConnectionAbortedError)


def _placeholder():
    img = np.full((360, 640, 3), 40, np.uint8)
    cv2.putText(img, "Sin imagen todavia", (150, 190), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (200, 200, 200), 2)
    return img


PLACEHOLDER = _placeholder()


class Handler(BaseHTTPRequestHandler):
    server_version = "AgroVisionLocal"
    motor: Motor = None  # lo asigna main()

    def log_message(self, fmt, *args):  # silencia el log por petición (hay polling)
        pass

    # ------------------------------------------------------------ helpers
    def _origen_valido(self):
        origen = self.headers.get("Origin")
        if not origen:
            return True
        puerto = self.server.server_address[1]
        return origen in (f"http://127.0.0.1:{puerto}", f"http://localhost:{puerto}")

    def _json(self, datos, codigo=200):
        cuerpo = json.dumps(datos, ensure_ascii=False).encode("utf-8")
        self.send_response(codigo)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(cuerpo)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(cuerpo)

    def _accion(self, resultado):
        ok, msg = resultado
        self._json({"ok": ok, "mensaje": msg}, 200 if ok else 400)

    # ---------------------------------------------------------------- GET
    def do_GET(self):
        if not self._origen_valido():
            return self._json({"ok": False, "mensaje": "Origen no permitido"}, 403)
        url = urlparse(self.path)
        if url.path == "/api/estado":
            return self._json(self.motor.estado_json())
        if url.path == "/api/dashboard":
            return self._json(self.motor.dashboard_json())
        if url.path == "/video":
            vista = parse_qs(url.query).get("vista", ["detecciones"])[0]
            return self._video(vista)
        if url.path == "/api/registro.csv":
            return self._csv(parse_qs(url.query).get("formato", ["excel"])[0])
        if url.path == "/api/vista.png":
            return self._png()
        return self._estatico(url.path)

    def _estatico(self, ruta):
        ruta = "/index.html" if ruta == "/" else ruta
        archivo = (ESTATICOS / ruta.lstrip("/")).resolve()
        if ESTATICOS.resolve() not in archivo.parents or not archivo.is_file():
            return self._json({"ok": False, "mensaje": "No encontrado"}, 404)
        tipo = mimetypes.guess_type(archivo.name)[0] or "application/octet-stream"
        datos = archivo.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", f"{tipo}; charset=utf-8" if tipo.startswith("text/") or tipo.endswith("javascript") else tipo)
        self.send_header("Content-Length", str(len(datos)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(datos)

    def _video(self, vista):
        self.send_response(200)
        self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        ultimo_id, ultimo_envio = -1, 0.0
        try:
            while True:
                img, fid = self.motor.imagen(vista)
                ahora = time.monotonic()
                # Reenvía cada 1 s aunque no haya cambios: así detectamos clientes desconectados.
                if fid != ultimo_id or ahora - ultimo_envio > 1.0:
                    ok, jpg = cv2.imencode(".jpg", PLACEHOLDER if img is None else img,
                                           [cv2.IMWRITE_JPEG_QUALITY, 80])
                    if ok:
                        datos = jpg.tobytes()
                        self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\n"
                                         + f"Content-Length: {len(datos)}\r\n\r\n".encode()
                                         + datos + b"\r\n")
                        ultimo_id, ultimo_envio = fid, ahora
                time.sleep(0.04)
        except ERRORES_CLIENTE:
            return

    def _csv(self, formato="excel"):
        ok, resultado = self.motor.exportar_csv(formato)
        if not ok:
            return self._json({"ok": False, "mensaje": resultado}, 400)
        datos = Path(resultado).read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/csv; charset=utf-8")
        self.send_header("Content-Disposition", f'attachment; filename="{Path(resultado).name}"')
        self.send_header("Content-Length", str(len(datos)))
        self.end_headers()
        self.wfile.write(datos)

    def _png(self):
        img, _ = self.motor.imagen("detecciones")
        if img is None:
            return self._json({"ok": False, "mensaje": "No hay vista anotada todavía"}, 400)
        datos = cv2.imencode(".png", img)[1].tobytes()
        self.send_response(200)
        self.send_header("Content-Type", "image/png")
        self.send_header("Content-Disposition", 'attachment; filename="vista_anotada.png"')
        self.send_header("Content-Length", str(len(datos)))
        self.end_headers()
        self.wfile.write(datos)

    # --------------------------------------------------------------- POST
    def do_POST(self):
        if not self._origen_valido():
            return self._json({"ok": False, "mensaje": "Origen no permitido"}, 403)
        url = urlparse(self.path)
        consulta = parse_qs(url.query)
        m = self.motor
        if url.path == "/api/iniciar":
            return self._accion(m.iniciar())
        if url.path == "/api/detener":
            return self._accion(m.detener())
        if url.path == "/api/repetir":
            return self._accion(m.repetir())
        if url.path == "/api/fuente/muestra":
            return self._accion(m.fijar_muestra())
        if url.path == "/api/fuente/camara":
            try:
                return self._accion(m.fijar_camara(int(consulta.get("n", ["0"])[0])))
            except ValueError:
                return self._accion((False, "Número de cámara inválido"))
        if url.path == "/api/fuente/archivo":
            return self._subida(consulta.get("nombre", [""])[0])
        if url.path == "/api/hsv":
            try:
                largo = min(int(self.headers.get("Content-Length", "0")), 4096)
                datos = json.loads(self.rfile.read(largo) or b"{}")
                return self._accion(m.fijar_hsv(datos["min"], datos["max"]))
            except (ValueError, KeyError, TypeError):
                return self._accion((False, "Cuerpo inválido: se espera {min:[h,s,v], max:[h,s,v]}"))
        if url.path == "/api/roi":
            try:
                largo = min(int(self.headers.get("Content-Length", "0")), 4096)
                d = json.loads(self.rfile.read(largo) or b"{}")
                if d.get("completa"):
                    return self._accion(m.restablecer_roi())
                return self._accion(m.fijar_roi(d["x"], d["y"], d["w"], d["h"]))
            except (ValueError, KeyError, TypeError, AttributeError):
                return self._accion((False, "Cuerpo inválido: se espera {x, y, w, h} o {completa: true}"))
        if url.path == "/api/cola/quitar":
            try:
                return self._accion(m.quitar(int(consulta.get("i", [""])[0])))
            except ValueError:
                return self._accion((False, "Posición inválida"))
        if url.path == "/api/cola/mover":
            try:
                return self._accion(m.mover(int(consulta.get("de", [""])[0]), int(consulta.get("a", [""])[0])))
            except ValueError:
                return self._accion((False, "Posiciones inválidas"))
        if url.path == "/api/cola/vaciar":
            return self._accion(m.vaciar())
        return self._json({"ok": False, "mensaje": "No encontrado"}, 404)

    def _subida(self, nombre):
        try:
            largo = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            largo = 0
        if not nombre or largo <= 0:
            return self._accion((False, "Falta el archivo"))
        if largo > MAX_SUBIDA:
            return self._accion((False, "Archivo demasiado grande (máx. 500 MB)"))
        destino = self.motor.ruta_subida(nombre)
        restante = largo
        try:
            with open(destino, "wb") as f:
                while restante > 0:
                    trozo = self.rfile.read(min(1024 * 1024, restante))
                    if not trozo:
                        break
                    f.write(trozo)
                    restante -= len(trozo)
        except OSError as exc:
            return self._accion((False, f"No se pudo guardar el archivo: {exc}"))
        if restante > 0:
            return self._accion((False, "La subida se interrumpió"))
        self._accion(self.motor.fijar_archivo(destino, nombre))


def main():
    parser = argparse.ArgumentParser(description="AgroVision — interfaz web local")
    parser.add_argument("--puerto", type=int, default=8000)
    args = parser.parse_args()

    Handler.motor = Motor()
    servidor = ThreadingHTTPServer(("127.0.0.1", args.puerto), Handler)
    servidor.daemon_threads = True
    print(f"AgroVision en http://127.0.0.1:{args.puerto}  (Ctrl+C para salir)")
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        Handler.motor.cerrar()
        servidor.server_close()


if __name__ == "__main__":
    main()
