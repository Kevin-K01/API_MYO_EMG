from flask import Flask, request, jsonify
from flask_socketio import SocketIO
import myo
from collections import deque
from threading import Lock, Thread
import csv
import os
from flask_cors import CORS

app = Flask(__name__)
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*")
file_lock = Lock()
CSV_FILE = "datos_pacientes.csv"
DATA_DIR = "pacientes"
os.makedirs(DATA_DIR, exist_ok=True)

def initialize_csv():
    if not os.path.exists(CSV_FILE):
        with open(CSV_FILE, mode="w", newline="") as file:
            writer = csv.writer(file)
            writer.writerow(["nombre", "curp", "Extremidad_Afectada", "observaciones"])
initialize_csv()

@app.route('/')
def root():
    return "Servidor Flask-SocketIO para Myo y React"

@app.route("/add_patient", methods=["POST"])
def add_patient():
    data = request.json
    if not all(k in data for k in ["nombre", "curp", "Extremidad_Afectada", "observaciones"]):
        return {"error": "Datos incompletos"}, 400

    patient_file = os.path.join(DATA_DIR, f"{data['curp']}")
    patient_exists = False

    # Comprobamos si el paciente ya existe en el archivo CSV
    with open(CSV_FILE, mode="r", newline="") as file:
        reader = csv.DictReader(file)
        for row in reader:
            if row["curp"] == data["curp"]:
                patient_exists = True
                break

    if patient_exists:
        return {"error": "El paciente ya está registrado"}, 400

    # Crear una carpeta para cada paciente
    os.makedirs(patient_file, exist_ok=True)
    # Asignar el directorio del paciente al collector
    EmgCollector.current_patient_file = patient_file  # Asignamos la carpeta a la clase



    # Agregar la información del paciente al archivo principal de pacientes
    with open(CSV_FILE, mode="a", newline="") as file:
        writer = csv.writer(file)
        writer.writerow([data["nombre"], data["curp"], data["Extremidad_Afectada"], data["observaciones"]])

    print(f"Paciente {data['nombre']} con CURP {data['curp']} agregado correctamente.")

    return {"message": "Paciente agregado correctamente"}, 200

class EmgCollector(myo.DeviceListener):
    def __init__(self, n):
        self.n = n
        self.lock = Lock()
        self.emg_data_queue = deque(maxlen=n)
        self.selected_sensors = [True] * 8
        self.is_recording = False
        self.emg_buffer = []
        self.session_data = []
        self.current_patient_file = None
        self.session_number = None  # Para almacenar el número de sesión
        self.observations = None  # Para almacenar las observaciones

    def on_connected(self, event):
        event.device.stream_emg(True)
        print("Dispositivo Myo conectado. Transmisión EMG habilitada")

    def on_emg(self, event):
        with self.lock:
            filtered_emg = [event.emg[i] for i in range(8) if self.selected_sensors[i]]
            self.emg_data_queue.append((event.timestamp, filtered_emg))
            socketio.emit('emg_data', {'timestamp': event.timestamp, 'emg': filtered_emg})

            if self.is_recording:
                if self.session_number is not None and self.observations is not None:
                    # Aquí agregamos la sesión y observaciones a los datos EMG
                    self.emg_buffer.append((self.session_number, self.observations, event.timestamp, filtered_emg))
                    print(f"Datos añadidos al buffer: {self.emg_buffer[-1]}")  # Verifica si los datos se están agregando

    def save_data(self):
        if self.current_patient_file and self.emg_buffer:
            # Extraer el nombre del paciente de la ruta del archivo
            patient_name = os.path.splitext(os.path.basename(self.current_patient_file))[0]
            patient_directory = os.path.join("pacientes", patient_name)
            os.makedirs(patient_directory, exist_ok=True)

            # Archivos separados por paciente
            session_file = os.path.join(patient_directory, f"{patient_name}_sesiones.csv")
            emg_file = os.path.join(patient_directory, f"{patient_name}_datos_emg.csv")

            # Guardar los datos de sesión y observaciones (si no existen aún los encabezados)
            if not os.path.exists(session_file):
                with open(session_file, mode="a", newline="", encoding="utf-8") as file:
                    writer = csv.writer(file)

                    # Escribir encabezados en el archivo de sesiones solo una vez
                    writer.writerow(["sesion", "observaciones"])
                    print("Escribiendo encabezados de sesiones...")

            # Siempre agregar una nueva sesión con sus observaciones
            with open(session_file, mode="a", newline="", encoding="utf-8") as file:
                writer = csv.writer(file)
                writer.writerow([self.session_number, self.observations])

            # Guardar datos EMG
            if not os.path.exists(emg_file):
                with open(emg_file, mode="a", newline="", encoding="utf-8") as file:
                    writer = csv.writer(file)

                    # Escribir encabezados en el archivo de datos EMG solo una vez
                    writer.writerow([
                        "timestamp", "sensor1", "sensor2", "sensor3", "sensor4",
                        "sensor5", "sensor6", "sensor7", "sensor8"
                    ])
                    print("Escribiendo encabezados de datos EMG...")

            # Guardar los datos EMG (sensores 1-8) cada vez que se capture
            with open(emg_file, mode="a", newline="", encoding="utf-8") as file:
                writer = csv.writer(file)

                # Guardar los datos EMG (sensores 1-8) con su timestamp
                for row in self.emg_buffer:
                    emg_data = row[3]  # Datos EMG (sensores 1-8)
                    timestamp = row[2]  # Timestamp
                    writer.writerow([timestamp] + emg_data)  # Guardar timestamp + datos EMG
                    print(f"Guardando fila de datos EMG: {[timestamp] + emg_data}")

            # Limpiar el buffer de datos EMG después de guardar
            self.emg_buffer = []
            print("Datos guardados y buffer limpiado.")


@app.route("/start_emg_capture", methods=["POST"])
def start_emg_capture():
    data = request.json
    required_keys = ["nombre", "sesion", "observaciones"]
    if not all(key in data for key in required_keys):
        return {"error": f"Faltan datos: {', '.join([key for key in required_keys if key not in data])}"}, 400

    patient_file = None
    patient_curp = None
    with open(CSV_FILE, mode="r", newline="") as file:
        reader = csv.DictReader(file)
        patient_found = False  # Variable para saber si encontramos el paciente
        for row in reader:
            if row["nombre"].strip().upper() == data["nombre"].strip().upper():
                patient_curp = row["curp"]
                patient_file = os.path.join(DATA_DIR, f"{patient_curp}")
                patient_found = True
                break

        if not patient_found:
            return {"error": f"Paciente con nombre '{data['nombre']}' no encontrado en el registro."}, 400

    rec_emg.listener.is_recording = True
    rec_emg.listener.current_patient_file = patient_file
    rec_emg.listener.session_number = str(data["sesion"])  # Asignar el número de sesión
    rec_emg.listener.observations = str(data["observaciones"])  # Asignar las observaciones
    print(f"Iniciando captura de EMG para {data['nombre']}, archivo: {patient_file}")

    return {"message": "Captura de EMG iniciada", "exists": True}, 200

@app.route("/stop_emg_capture", methods=["POST"])
def stop_emg_capture():
    if rec_emg.listener.is_recording:
        rec_emg.listener.is_recording = False
        rec_emg.listener.save_data()
        rec_emg.listener.current_patient_file = None
        print("Captura de EMG detenida y datos guardados")

    return {"message": "Captura de EMG detenida y datos guardados"}, 200

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
    global rec_emg
    rec_emg = RecEmg()
    rec_emg.iniciar()

if __name__ == '__main__':
    thread_flask = Thread(target=socketio.run, args=(app,), kwargs={"debug": True, "use_reloader": False, "allow_unsafe_werkzeug": True})
    thread_flask.start()

    thread_myo = Thread(target=start_myo_data_collection)
    thread_myo.start()


