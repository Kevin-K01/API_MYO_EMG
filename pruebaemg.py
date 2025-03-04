import myo
import time
import datetime
import csv
from collections import deque
from threading import Lock, Timer


class EmgCollector(myo.DeviceListener):
    """
    Recolecta los datos EMG desde el dispositivo Myo.
    """

    def __init__(self, n, save_time=1):
        super().__init__()
        self.n = n  # Número máximo de muestras en la cola
        self.lock = Lock()  # Para asegurar que las operaciones sobre los datos sean seguras
        self.emg_data_queue = deque(maxlen=n)  # Cola para almacenar los últimos datos EMG
        self.is_collecting = False
        self.emg_data = []  # Lista para almacenar los datos EMG completos
        self.save_time = save_time  # Tiempo para guardar los datos en minutos
        self.filename = None
        self.selected_sensors = [True] * 8  # Todos los sensores están habilitados
        self.start_time = None
        self.emg_count = 0  # Contador de datos EMG recibidos

    def on_connected(self, event):
        """
        Habilita la transmisión de datos EMG al conectar el dispositivo.
        """
        event.device.stream_emg(True)
        print("Dispositivo Myo conectado. Transmisión EMG habilitada.")

    def on_emg(self, event):
        """
        Procesa los eventos EMG recibidos.
        """
        with self.lock:
            # Filtra los datos EMG según los sensores seleccionados
            filtered_emg = [event.emg[i] for i in range(8) if self.selected_sensors[i]]
            self.emg_data.append(filtered_emg)
            self.emg_data_queue.append((event.timestamp, event.emg))  # Añade los datos a la cola
            self.emg_count += 1  # Incrementa el contador de datos EMG

    def save_data(self):
        """
        Guarda los datos EMG recolectados en un archivo CSV.
        """
        if self.emg_data_queue:  # Verifica si hay datos para guardar
            filename = f"emg_data_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            with open(filename, 'w', newline='') as file:
                writer = csv.writer(file)
                writer.writerow(["Timestamp", "EMG Data"])  # Encabezado del CSV
                for timestamp, emg in self.emg_data_queue:
                    writer.writerow([timestamp, emg])
            print(f"Datos guardados en {filename}")
            print(f"Total de datos EMG guardados: {len(self.emg_data_queue)}")  # Muestra la cantidad de datos guardados
            self.emg_data_queue.clear()  # Limpia la cola después de guardar los datos


class RecEmg:
    """
    Administra la recolección de datos EMG.
    """

    def __init__(self, duration=10, unit='seconds', save_time=1):
        myo.init()  # Inicializa el Myo SDK
        self.listener = EmgCollector(512, save_time)  # Recolector de datos EMG
        self.hub = myo.Hub()
        self.duration = duration
        self.unit = unit
        self.save_time = save_time
        self.start_time = None
        self.timer = None

    def _convert_to_seconds(self, duration, unit):
        """
        Convierte la duración y la unidad a segundos.
        """
        if unit == 'seconds':
            return duration
        elif unit == 'minutes':
            return duration * 60
        elif unit == 'hours':
            return duration * 3600
        else:
            raise ValueError("Unidad no válida. Usa 'seconds', 'minutes' o 'hours'.")

    def iniciar(self):
        """
        Inicia la recolección de datos EMG durante el tiempo especificado, guardando los datos cada intervalo.
        """
        try:
            print(f"Iniciando recolección de datos EMG durante {self.duration} {self.unit}...")

            # Ejecuta el hub de Myo para procesar los datos
            self.hub.run_forever(self.listener, 1000)  # Ejecuta el hub de manera indefinida cada 1000 ms (1 segundo)

            self.start_time = time.time()
            last_save_time = self.start_time

            # Función de guardado de datos en intervalos
            def save_data_periodically():
                nonlocal last_save_time
                elapsed_time = time.time() - last_save_time
                print(elapsed_time)
                if elapsed_time >= self._convert_to_seconds(self.save_time, 'seconds'):
                    print(f"Guardando datos EMG después de {self.save_time} segundos.")
                    self.listener.save_data()  # Guarda los datos en el archivo
                    last_save_time = time.time()  # Reinicia el contador de tiempo

                # Si el tiempo no ha expirado, vuelve a programar el guardado
                if time.time() - self.start_time < self._convert_to_seconds(self.duration, self.unit):
                    self.timer = Timer(0.5, save_data_periodically)  # Llama nuevamente después de 0.5 segundos
                    self.timer.start()

            # Comienza el ciclo de guardado periódicamente
            self.timer = Timer(0.5, save_data_periodically)  # Llama a la función inmediatamente
            self.timer.start()

        except KeyboardInterrupt:
            print("\nAplicación detenida.")
        finally:
            self.detener()

    def detener(self):
        """
        Detiene la recolección de datos y apaga el hub de Myo.
        """
        try:
            if self.timer is not None:
                self.timer.cancel()  # Cancela cualquier tarea programada si existe
            self.hub.shutdown()
            print("Recolección de datos EMG detenida.")
        except AttributeError:
            pass


if __name__ == "__main__":
    duration = 1  # Duración total en minutos (puedes cambiarlo)
    unit = 'seconds'  # 'seconds', 'minutes', 'hours'
    save_time = 1  # Guardar cada 1 segundo (puedes cambiarlo a 60 para guardar cada minuto)

    recolector = RecEmg(duration, unit, save_time)
    recolector.iniciar()

    print(f"Datos EMG obtenidos por {duration} {unit}.")

