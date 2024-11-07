import serial
import time

# Настройки порта (измените по необходимости)
UART_PORT = "/dev/pts/6"  # Укажите нужный порт или виртуальный порт
BAUD_RATE = 9600

# Эмуляция данных вышек
towers_data = [
    "+CENG: 0,\"250\",\"01\",\"1001\",\"55432123\",\"37321234\"",
    "+CENG: 1,\"250\",\"01\",\"1002\",\"55432123\",\"37321334\"",
    "+CENG: 2,\"250\",\"01\",\"1003\",\"55432123\",\"37321434\"",
    "+CENG: 3,\"250\",\"01\",\"1004\",\"55432123\",\"37321534\"",
    "+CENG: 4,\"250\",\"01\",\"1005\",\"55432123\",\"37321634\""
]

def simulate_response(command):
    """Эмуляция ответа на команды."""
    if command.strip() == "AT+CENG=1,1":
        return "OK"  # Подтверждение настройки
    elif command.strip() == "AT+CENG?":
        # Возвращаем эмулированные данные вышек
        return "\n".join(towers_data) + "\nOK"
    else:
        return "ERROR"  # Ошибка для нераспознанной команды

def main():
    # Открываем UART порт
    with serial.Serial(UART_PORT, BAUD_RATE, timeout=1) as ser:
        print(f"Ожидание команд на {UART_PORT}...")

        # Очистка входного буфера при старте
        ser.reset_input_buffer()
        
        # Читаем команды в бесконечном цикле
        while True:
            if ser.in_waiting > 0:
                # Читаем команду
                command = ser.readline().decode('utf-8').strip()
                print(f"Получена команда: {command}")
                
                # Генерируем ответ
                response = simulate_response(command)
                print(f"Отправка ответа: {response}")
                
                # Отправляем ответ обратно
                ser.write((response + "\r\n").encode('utf-8'))

            # Небольшая задержка для циклического опроса
            time.sleep(0.1)

if __name__ == "__main__":
    main()
