import sys
import pandas as pd
import numpy as np
import os
import serial
from PyQt5 import QtWidgets, QtGui, QtCore
import pyqtgraph as pg
import glob
import time
import threading

MAP_IMAGE_PATH = "alidade_satellite.jpg"
TOWERS_DATA_PATH = "250.csv"
MAX_TOWERS_DISPLAY = 2000
MOSCOW_CENTER_LON = 37.618423
MOSCOW_CENTER_LAT = 55.751244
MAP_ZOOM = 13

UART_PORT = "/dev/pts/7"  # Укажите правильный порт, например, /dev/pts/3, если используете виртуальный порт с socat
BAUD_RATE = 9600

class Sim800Emulator(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.tower_markers = []  # Список для хранения маркеров вышек
        self.setWindowTitle("Эмулятор SIM800 с картой Москвы")
        self.setGeometry(100, 100, 800, 600)

        central_widget = QtWidgets.QWidget()
        self.setCentralWidget(central_widget)
        layout = QtWidgets.QVBoxLayout(central_widget)

        control_layout = QtWidgets.QHBoxLayout()
        layout.addLayout(control_layout)

        # Поля для ввода радиуса и скорости
        self.radius_input = QtWidgets.QLineEdit()
        self.radius_input.setPlaceholderText("Радиус (м)")
        self.speed_input = QtWidgets.QLineEdit()
        self.speed_input.setPlaceholderText("Скорость (м/с)")
        control_layout.addWidget(QtWidgets.QLabel("Радиус:"))
        control_layout.addWidget(self.radius_input)
        control_layout.addWidget(QtWidgets.QLabel("Скорость:"))
        control_layout.addWidget(self.speed_input)

        # Кнопка "Начать симуляцию"
        self.start_button = QtWidgets.QPushButton("Начать симуляцию")
        self.start_button.clicked.connect(self.start_simulation)
        control_layout.addWidget(self.start_button)

        # Кнопка "Сброс"
        self.reset_button = QtWidgets.QPushButton("Сброс")
        self.reset_button.clicked.connect(self.reset_simulation)
        control_layout.addWidget(self.reset_button)

        self.output_text_area = QtWidgets.QTextEdit()
        self.output_text_area.setReadOnly(True)
        layout.addWidget(self.output_text_area)

        self.input_text_area = QtWidgets.QTextEdit()
        self.input_text_area.setReadOnly(True)
        layout.addWidget(self.input_text_area)

        self.map_view = pg.PlotWidget()
        layout.addWidget(self.map_view)
        self.map_view.setAspectLocked(True)
        self.map_view.setRange(QtCore.QRectF(MOSCOW_CENTER_LON - 0.04, MOSCOW_CENTER_LAT - 0.04, 0.08, 0.08))

        self.towers = None
        self.add_background_image()
        self.load_towers()
        self.init_drone()

        self.waypoints = []
        self.trajectory_lines = []
        self.drone_marker = None
        self.current_waypoint_index = 0
        self.is_moving = False
        self.detection_radius = 0
        self.detection_circle = None
        self.detected_towers_set = set()
        self.map_view.scene().sigMouseClicked.connect(self.add_waypoint)

        # Настройка UART соединений
        self.receive_port = "/dev/pts/6"
        self.send_port = "/dev/pts/7"
        self.baud_rate = 9600
        self.setup_uart_connections()

        # Таймер для обработки команд
        self.command_timer = QtCore.QTimer(self)
        self.start_uart_listener()
        self.command_timer.start(1000)

        try:
            with serial.Serial(self.send_port, BAUD_RATE, timeout=1) as ser:
                print(f"Подключение к порту {self.send_port}")

                # Отправляем команду для настройки
                self.send_command(ser, "AT+CENG=1,1")
        except serial.SerialException as e:
            print(f"Ошибка при подключении к UART: {e}")

    def add_waypoint(self, event):
        """Добавляет точки пути и активирует кнопку запуска после добавления точки."""
        mouse_point = self.map_view.plotItem.vb.mapSceneToView(event.scenePos())
        waypoint_lon = mouse_point.x()
        waypoint_lat = mouse_point.y()

        self.waypoints.append((waypoint_lon, waypoint_lat))

        waypoint_item = pg.ScatterPlotItem(
            x=[waypoint_lon], y=[waypoint_lat], pen=pg.mkPen(None), brush=pg.mkBrush(255, 255, 0, 255), size=10
        )
        self.map_view.addItem(waypoint_item)
        self.start_button.setEnabled(True)  # Активируем кнопку "Начать симуляцию"
        
        # Сохраняем маркеры для сброса
        self.tower_markers.append(waypoint_item)

    def reset_simulation(self):
        """Сбрасывает все состояния, останавливает процессы и очищает карту."""
        # Останавливаем таймеры
        if hasattr(self, 'drone_timer'):
            self.drone_timer.stop()
        self.command_timer.stop()

        # Очищаем маркеры вышек и траекторию
        for marker in self.tower_markers:
            self.map_view.removeItem(marker)
        self.tower_markers.clear()

        for line in self.trajectory_lines:
            self.map_view.removeItem(line)
        self.trajectory_lines = []

        if self.drone_marker:
            self.map_view.removeItem(self.drone_marker)
            self.drone_marker = None

        if self.detection_circle:
            self.map_view.removeItem(self.detection_circle)
            self.detection_circle = None

        # Сбрасываем состояние симуляции
        self.waypoints.clear()
        self.current_waypoint_index = 0
        self.is_moving = False
        print("Симуляция сброшена.")

    def setup_uart_connections(self):
        """Настраивает соединения UART для приема и отправки данных."""
        try:
            self.receive_connection = serial.Serial(self.receive_port, self.baud_rate, timeout=1)
            print(f"Прием на UART порту {self.receive_port}")
            self.send_connection = serial.Serial(self.send_port, self.baud_rate, timeout=1)
            print(f"Отправка на UART порту {self.send_port}")
        except serial.SerialException as e:
            print(f"Ошибка при подключении к UART: {e}")

    def start_uart_listener(self):
        """Запускает поток для постоянного прослушивания UART-порта."""
        uart_thread = threading.Thread(target=self.respond_to_uart_commands, daemon=True)
        uart_thread.start()

    def respond_to_uart_commands(self):
        """Поток, который непрерывно слушает UART-порт для получения команд и немедленно отвечает."""
        UART_PORT = self.receive_port
        BAUD_RATE = self.baud_rate

        try:
            with serial.Serial(UART_PORT, BAUD_RATE, timeout=1) as ser:
                print(f"Прослушивание команд на {UART_PORT}...")

                # Очистка входного буфера при старте
                ser.reset_input_buffer()

                # Непрерывное чтение команд
                while True:
                    if ser.in_waiting > 0:
                        # Чтение команды
                        command = ser.readline().decode('utf-8').strip()
                        print(f"Получена команда: {command}")

                        # Обработка команды
                        if command == "AT+CENG?":
                            # Если команда AT+CENG?, отправляем данные вышек
                            response = self.send_tower_data()
                        elif command == "AT+CENG=1,1":
                            # Команда активации режима отчета о сотах
                            response = "OK"
                        else:
                            # Ответ по умолчанию на нераспознанные команды
                            response = "ERROR"

                        # Отправляем ответ
                        ser.write((response + "\r\n").encode('utf-8'))
                        print(f"Отправка ответа: {response}")

                    # Короткая задержка для предотвращения чрезмерного использования ресурсов
                    time.sleep(0.05)

        except serial.SerialException as e:
            print(f"Ошибка при подключении к UART: {e}")

    def send_tower_data(self):
        """Возвращает данные о 7 ближайших вышках в формате CENG."""
        if self.drone_position is None or not isinstance(self.drone_position, np.ndarray):
            print("Ошибка: координаты дрона не установлены.")
            return "ERROR"

        # Вычисляем расстояние от дрона до каждой вышки и сортируем по ближайшим
        towers_with_distance = [
            (lon, lat, mcc, mnc, cell, np.linalg.norm(self.drone_position - np.array([lon, lat])))
            for lon, lat, mcc, mnc, cell in self.towers
        ]
        towers_with_distance.sort(key=lambda x: x[5])  # Сортируем по расстоянию
        nearest_towers = towers_with_distance[:7]  # Берем 7 ближайших вышек

        # Формируем данные о вышках в требуемом формате
        tower_data_lines = []
        for i, (lon, lat, mcc, mnc, cell, distance) in enumerate(nearest_towers):
            if i == 0:
                # Первая вышка с дополнительной информацией
                line = f'+CENG: {i},"0034,{int(distance)},00,{mcc},{mnc},40,{cell:04x},01,05,6d07,255"'
            else:
                # Остальные вышки с сокращенной информацией
                line = f'+CENG: {i},"0072,{int(distance)},44,{cell:04x},{mcc},{mnc},6d07"'
            tower_data_lines.append(line)

        # Объединяем строки с вышками и добавляем "OK" в конце
        tower_data = "\n".join(tower_data_lines)
        
        print("Отправлены данные о вышках:\n" + tower_data)
        return tower_data  # Возвращаем все данные как единую строку



    def load_towers(self):
        self.towers_df = pd.read_csv(TOWERS_DATA_PATH)
        if len(self.towers_df) > MAX_TOWERS_DISPLAY:
            self.towers_df = self.towers_df.sample(n=MAX_TOWERS_DISPLAY, random_state=1)
    
        latitudes = self.towers_df['lat'].values
        longitudes = self.towers_df['lon'].values
        mccs = self.towers_df['mcc'].values
        mncs = self.towers_df['area'].values  # Получаем MNC
        cells = self.towers_df['cell'].values
    
        self.tower_scatter = pg.ScatterPlotItem(
            x=longitudes, y=latitudes, pen=pg.mkPen(None), brush=pg.mkBrush(0, 0, 255, 120), size=5
        )
        self.map_view.addItem(self.tower_scatter)
        self.towers = list(zip(longitudes, latitudes, mccs, mncs, cells))  # Добавляем MNC в список вышек

    def update_tower_colors(self):
        """Обновляет цвета вышек на карте, отображая только вышки, полученные по UART, с сопоставлением в БД."""
        # Удаляем старые маркеры вышек, оставляя другие элементы
        for marker in self.tower_markers:
            self.map_view.removeItem(marker)
        self.tower_markers.clear()
        
        detected_towers = []  # Список для хранения обнаруженных вышек с координатами

        # Запрашиваем данные о вышках по UART
        try:
            with serial.Serial(self.send_port, self.baud_rate, timeout=1) as ser:
                print(f"Подключение к порту {self.send_port}")
                
                # Отправляем команду для запроса данных о вышках и получаем ответ
                response = self.send_command(ser, "AT+CENG?")
                print(f"Получены данные о вышках: {response}")
                
                # Парсим данные о вышках из ответа
                detected_tower_data = []  # Для координат вышек
                detected_tower_text = []  # Для текстового отображения
                
                lines = response.strip().splitlines()
                for line in lines:
                    if line.startswith("+CENG:"):
                        try:
                            parts = line.split(",", 1)
                            if len(parts) < 2:
                                continue
                            
                            # Извлекаем данные для первой вышки и остальных вышек с учетом формата
                            cell_info = parts[1].strip('"').split(',')
                            if len(cell_info) == 11:
                                signal = int(cell_info[1])
                                mcc = int(cell_info[3])
                                mnc = int(cell_info[4])
                                cellid = cell_info[6]
                            elif len(cell_info) == 7:
                                signal = int(cell_info[1])
                                cellid = cell_info[3]
                                mcc = int(cell_info[4])
                                mnc = int(cell_info[5])
                            else:
                                print(f"Неподдерживаемый формат строки вышки: {line}")
                                continue

                            # Сохраняем данные о вышке
                            detected_tower_data.append((mcc, mnc, cellid, signal))

                        except (ValueError, IndexError) as e:
                            print(f"Ошибка обработки строки вышки: {line} - {e}")
                
                # Получаем координаты для обнаруженных вышек и отображаем их на карте
                for mcc, mnc, cellid, signal in detected_tower_data:
                    tower_coordinates = self.find_tower_coordinates(mcc, mnc, cellid)
                    if tower_coordinates:
                        lon, lat = tower_coordinates
                        brush = pg.mkBrush(255, 0, 0)  # Красный для всех полученных вышек
                        tower_marker = pg.ScatterPlotItem(
                            x=[lon], y=[lat], pen=pg.mkPen(None), brush=brush, size=8
                        )
                        self.map_view.addItem(tower_marker)
                        self.tower_markers.append(tower_marker)  # Добавляем только маркеры вышек в список

                        # Добавляем текстовую информацию
                        detected_tower_text.append(f"Координаты: ({lon}, {lat}), Сигнал: {signal}")

                # Отображаем текстовую информацию о вышках
                self.display_detected_towers(detected_tower_text)

        except serial.SerialException as e:
            print(f"Ошибка при подключении к UART: {e}")


    def parse_tower_data(self, response):
        """Парсит данные о вышках из строки ответа и извлекает MCC, MNC, Cell ID и силу сигнала."""
        detected_towers = []
        lines = response.splitlines()
        for line in lines:
            if line.startswith("+CENG:"):
                try:
                    parts = line.split(",")
                    # Извлекаем параметры: MCC, MNC, Cell ID, сигнал
                    cell_info = parts[1].strip('"').split(',')
                    mcc = int(cell_info[3], 16)  # MCC из 16-ричной системы
                    mnc = int(cell_info[4])  # MNC
                    cellid = cell_info[5]  # Cell ID в 16-ричной системе
                    signal = int(cell_info[1])  # Уровень сигнала
                    detected_towers.append((mcc, mnc, cellid, signal))
                except (ValueError, IndexError) as e:
                    print(f"Ошибка обработки строки вышки: {line} - {e}")
        return detected_towers

    def find_tower_coordinates(self, mcc, mnc, cellid):
        """Находит координаты вышки по данным из БД."""
        cellid_dec = int(cellid, 16)  # Преобразуем Cell ID из 16-ричной системы в десятичную
        tower = self.towers_df[(self.towers_df['mcc'] == mcc) &
                            (self.towers_df['area'] == mnc) &
                            (self.towers_df['cell'] == cellid_dec)]
        if not tower.empty:
            return tower.iloc[0]['lon'], tower.iloc[0]['lat']
        else:
            return None

    
    def display_detected_towers(self, towers):
        if towers:  # Если есть новые обнаруженные вышки
            print("Обнаруженные вышки:")
            for tower_info in towers:
                print(tower_info)

    def add_background_image(self):
        map_pixmap = QtGui.QPixmap(MAP_IMAGE_PATH)
        if map_pixmap.isNull():
            print("Ошибка: Не удалось загрузить изображение карты.")
            return

        map_image = map_pixmap.transformed(QtGui.QTransform().rotate(90), mode=QtCore.Qt.SmoothTransformation)
        map_image = map_image.toImage()
        width, height = map_image.width(), map_image.height()
        map_image = map_image.convertToFormat(QtGui.QImage.Format_RGB32)
        ptr = map_image.bits()
        ptr.setsize(height * width * 4)
        img_array = np.array(ptr).reshape((height, width, 4))

        map_item = pg.ImageItem(img_array)
        scale_factor = 13
        map_item.setRect(MOSCOW_CENTER_LON - 0.04 * scale_factor, MOSCOW_CENTER_LAT - 0.04 * scale_factor, 0.08 * scale_factor, 0.08 * scale_factor)
        map_item.setZValue(-1)
        self.map_view.addItem(map_item)

    def init_drone(self):
        self.drone_position = np.array([MOSCOW_CENTER_LON, MOSCOW_CENTER_LAT])
        self.drone_marker = pg.ScatterPlotItem(
            x=[self.drone_position[0]], y=[self.drone_position[1]], pen=pg.mkPen(None), brush=pg.mkBrush(255, 0, 0, 255), size=8
        )
        self.map_view.addItem(self.drone_marker)

    def add_waypoint(self, event):
        mouse_point = self.map_view.plotItem.vb.mapSceneToView(event.scenePos())
        waypoint_lon = mouse_point.x()
        waypoint_lat = mouse_point.y()

        self.waypoints.append((waypoint_lon, waypoint_lat))

        waypoint_item = pg.ScatterPlotItem(
            x=[waypoint_lon], y=[waypoint_lat], pen=pg.mkPen(None), brush=pg.mkBrush(255, 255, 0, 255), size=10
        )
        self.map_view.addItem(waypoint_item)

        waypoint_number = len(self.waypoints)
        text_item = pg.TextItem(text=str(waypoint_number), anchor=(0.5, 0), color=(255, 255, 255))
        text_item.setPos(waypoint_lon, waypoint_lat + 0.002)
        self.map_view.addItem(text_item)

        self.update_trajectory()

        if len(self.waypoints) == 1:
            self.set_drone_marker(waypoint_lon, waypoint_lat)

    def set_drone_marker(self, lon, lat):
        if self.drone_marker:
            self.map_view.removeItem(self.drone_marker)

        self.drone_marker = pg.ScatterPlotItem(
            x=[lon], y=[lat], pen=pg.mkPen(None), brush=pg.mkBrush(255, 0, 0, 255), size=12
        )
        self.map_view.addItem(self.drone_marker)
        self.drone_position = np.array([lon, lat])
        self.update_detection_radius(float(self.radius_input.text()) if self.radius_input.text() else 0)

    def update_trajectory(self):
        # Удаляем старую траекторию
        for line in self.trajectory_lines:
            self.map_view.removeItem(line)
        self.trajectory_lines = []

        # Отрисовываем линии между вейпоинтами
        for i in range(1, len(self.waypoints)):
            line = pg.PlotDataItem(
                x=[self.waypoints[i - 1][0], self.waypoints[i][0]],
                y=[self.waypoints[i - 1][1], self.waypoints[i][1]],
                pen=pg.mkPen(color=(255, 255, 0), width=2)
            )
            self.map_view.addItem(line)
            self.trajectory_lines.append(line)

    def update_detection_radius(self, radius):
        if self.detection_circle:
            self.map_view.removeItem(self.detection_circle)

        self.detection_radius = radius
        if radius > 0:
            self.detection_circle = pg.CircleROI(
                pos=(self.drone_position[0] - radius / 111320, self.drone_position[1] - radius / 111320),
                size=(radius * 2 / 111320, radius * 2 / 111320),
                pen=pg.mkPen(color=(255, 0, 0), width=1),
                movable=False
            )
            self.map_view.addItem(self.detection_circle)
            self.update_tower_colors()

    def start_simulation(self):
        if not self.waypoints:
            print("Не установлены точки пути для симуляции.")
            return
        self.is_moving = True
        self.current_waypoint_index = 0
        self.drone_timer = QtCore.QTimer(self)
        self.drone_timer.timeout.connect(self.move_drone)
        self.drone_timer.start(1)  # Задаем таймер с интервалом в 5 миллисекунд (200 Гц)

    def send_command(self, ser, command):
        """Отправка команды на UART и получение ответа."""
        ser.write((command + "\r\n").encode('utf-8'))
        print(f"Отправлена команда: {command}")

        # Чтение ответа
        time.sleep(1)  # Небольшая задержка для получения ответа
        response = ser.read_all().decode('utf-8')
        print(f"Ответ: {response}")
        return response

    def move_drone(self):
        if self.is_moving and self.waypoints:
            current_waypoint = self.waypoints[self.current_waypoint_index]
            distance = np.sqrt((current_waypoint[0] - self.drone_position[0]) ** 2 + (current_waypoint[1] - self.drone_position[1]) ** 2)

            if distance < 0.001:
                self.current_waypoint_index += 1
                if self.current_waypoint_index >= len(self.waypoints):
                    self.is_moving = False
                    self.drone_timer.stop()  # Останавливаем таймер
                    return
                current_waypoint = self.waypoints[self.current_waypoint_index]

            # Обновляем позицию
            direction = (current_waypoint[0] - self.drone_position[0], current_waypoint[1] - self.drone_position[1])
            norm = np.sqrt(direction[0] ** 2 + direction[1] ** 2)
            if norm != 0:
                direction = (direction[0] / norm, direction[1] / norm)
                speed = float(self.speed_input.text()) if self.speed_input.text() else 1.0
                self.drone_position[0] += direction[0] * speed * 0.0001
                self.drone_position[1] += direction[1] * speed * 0.0001

            self.set_drone_marker(self.drone_position[0], self.drone_position[1])

            # Обновляем траекторию и радиус обнаружения
            self.update_trajectory()
            self.update_detection_radius(self.detection_radius)


if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    emulator = Sim800Emulator()
    emulator.show()
    sys.exit(app.exec_())
