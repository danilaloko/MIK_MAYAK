import serial
import time

# Настройки порта (измените, если используете другой порт или скорость)
UART_PORT = "/dev/pts/7"  # Укажите правильный порт, например, /dev/pts/3, если используете виртуальный порт с socat
BAUD_RATE = 9600
COMMAND_INTERVAL = 5  # Интервал между командами AT+CENG? в секундах

def send_command(ser, command):
    """Отправка команды на UART и получение ответа."""
    ser.write((command + "\r\n").encode('utf-8'))
    print(f"Отправлена команда: {command}")

    # Чтение ответа
    time.sleep(1)  # Небольшая задержка для получения ответа
    response = ser.read_all().decode('utf-8')
    print(f"Ответ: {response}")
    return response

def main():
    # Открываем UART порт
    try:
        with serial.Serial(UART_PORT, BAUD_RATE, timeout=1) as ser:
            print(f"Подключение к порту {UART_PORT}")

            # Отправляем команду для настройки
            send_command(ser, "AT+CENG=1,1")

            # Циклическая отправка команды AT+CENG?
            while True:
                send_command(ser, "AT+CENG?")
                time.sleep(COMMAND_INTERVAL)
    except serial.SerialException as e:
        print(f"Ошибка при подключении к UART: {e}")

if __name__ == "__main__":
    main()
