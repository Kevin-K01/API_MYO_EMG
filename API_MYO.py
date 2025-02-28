from flask import Flask,request,jsonify
from flask_socketio import SocketIO
import myo
from collections import deque
from threading import Lock, Thread
import csv
import os
from flask_cors import CORS  # Importar CORS

app = Flask(__name__)
CORS(app)  # Habilitar CORS para todas las rutas
socketio = SocketIO(app, cors_allowed_origins="*")  # Habilita CORS para recibir peticiones de React

CSV_FILE = "datos_pacientes.csv"
# Verificar si el archivo CSV existe, si no, crearlo con encabezados
def initialize_csv():
    if not os.path.exists(CSV_FILE):
        with open(CSV_FILE, mode="w", newline="") as file:
            writer = csv.writer(file)
            writer.writerow(["nombre", "sesion", "curp", "Extremidad_Afectada", "observaciones"])  # Cabeceras
initialize_csv()

@app.route('/')
def root():
    return "Servidor Flask-SocketIO para Myo y React"


@app.route("/add_patient", methods=["POST"])
def add_patient():
    data = request.json  # Datos recibidos de React (JSON)
    # Verificación de los datos recibidos
    print("Datos recibidos:", data)

    if not all(k in data for k in ["nombre", "sesion", "curp", "Extremidad_Afectada", "observaciones"]):
        return {"error": "Datos incompletos"}, 400

    # Verificar si la CURP ya existe en el archivo
    with open(CSV_FILE, mode="r", newline="") as file:
        reader = csv.DictReader(file)
        for row in reader:
            if row["curp"] == data["curp"]:
                return {"error": "CURP ya registrada"}, 409

    # Agregar datos al CSV
    with open(CSV_FILE, mode="a", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(
            [data["nombre"], data["sesion"], data["curp"], data["Extremidad_Afectada"], data["observaciones"]])

    return {"message": "Paciente agregado correctamente"}, 200


class EmgCollector(myo.DeviceListener):
    def __init__(self, n):
        self.n = n
        self.lock = Lock()
        self.emg_data_queue = deque(maxlen=n)
        self.selected_sensors = [True] * 8

    def on_connected(self, event):
        event.device.stream_emg(True)
        print("Dispositivo Myo conectado. Transmisión EMG habilitada")

    def on_emg(self, event):
        with self.lock:
            filtered_emg = [event.emg[i] for i in range(8) if self.selected_sensors[i]]
            self.emg_data_queue.append((event.timestamp, filtered_emg))

            # Emitir datos en tiempo real al frontend
            socketio.emit('emg_data', {'timestamp': event.timestamp, 'emg': filtered_emg})
            #print("Datos EMG:", filtered_emg)


class RecEmg:
    def __init__(self):
        myo.init()
        self.listener = EmgCollector(512)
        self.hub = myo.Hub()

    def iniciar(self):
        try:
            print("Iniciando recolección de datos EMG...")
            self.hub.run_forever(self.listener, 1000)
        except KeyboardInterrupt:
            print("\nAplicación detenida.")
        finally:
            self.detener()

    def detener(self):
        try:
            self.hub.stop()
            print("Recolección de datos EMG detenida.")
        except AttributeError:
            pass


def start_myo_data_collection():
    recolector = RecEmg()
    recolector.iniciar()


if __name__ == '__main__':
    # Iniciar el servidor Flask-SocketIO en un hilo separado
    thread_flask = Thread(target=socketio.run, args=(app,), kwargs={"debug": True, "use_reloader": False, "allow_unsafe_werkzeug": True})
    thread_flask.start()

    # Iniciar la recolección de datos Myo en otro hilo
    thread_myo = Thread(target=start_myo_data_collection)
    thread_myo.start()
