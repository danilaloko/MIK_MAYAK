// console_display.c
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <string.h>
#include "msg_definitions.h"
#include "geoprocessing.h"
#include "hashutils.h"
#include <math.h>

#define DISPLAY_SOCKET_PATH "/tmp/display_socket"
#define DISPLAY_COUNT 7
#define LOCATION_HISTORY_SIZE 10
#define LOG_FILE "location_log.txt"

size_t DBSIZE;

typedef struct {
    long msg_type;
    uint16_t MCC;
    uint16_t MNC;
    uint32_t CID;
    int receive_level;
    float LAT;
    float LONG;
} tower_info_t;

typedef struct {
    double x;
    double y;
    double r;
} Tower;

struct Location locationHistory[LOCATION_HISTORY_SIZE];

// Добавить новую координату в начало массива, сдвинув старые
void update_location_history(struct Location newLocation) {
    for (int i = LOCATION_HISTORY_SIZE - 1; i > 0; i--) {
        locationHistory[i] = locationHistory[i - 1];
    }
    locationHistory[0] = newLocation;
}

double estimateDistance(double RSSI, double A, double n) {
    return pow(10, (A + RSSI) / (10 * n));
}

void trilateration(Tower towers[], int num_towers, double *x, double *y) {
    double x1 = towers[0].x, y1 = towers[0].y, r1 = towers[0].r;
    double x2 = towers[1].x, y2 = towers[1].y, r2 = towers[1].r;
    double x3 = towers[2].x, y3 = towers[2].y, r3 = towers[2].r;

    double A = 2 * (x2 - x1);
    double B = 2 * (y2 - y1);
    double C = r1*r1 - r2*r2 - x1*x1 + x2*x2 - y1*y1 + y2*y2;
    double D = 2 * (x3 - x2);
    double E = 2 * (y3 - y2);
    double F = r2*r2 - r3*r3 - x2*x2 + x3*x3 - y2*y2 + y3*y3;

    *x = (C * E - F * B) / (A * E - B * D);
    *y = (A * F - D * C) / (A * E - B * D);
}


// Функция трилатерации
struct Location trilaterate(tower_info_t *towers, uint8_t towerCount) {
    double totalX = 0.0, totalY = 0.0;
    double totalWeight = 0.0;

    double A = -40; // RSSI на расстоянии 1 метр
    double n = 3;   // Показатель затухания сигнала

    Tower coord_towers[towerCount];

    for (int i = 0; i < towerCount; i++) {
        if (towers[i].receive_level == 0) {
            continue;  // Пропускаем вышки с нулевым уровнем сигнала
        }
        
        coord_towers[i].x = towers[i].LAT;
        coord_towers[i].y = towers[i].LONG;
        coord_towers[i].r = estimateDistance(towers[i].receive_level, A, n);//pow(10, (towers[i].receive_level - 20 * log10(900e6) + 147.55) / 20);  // Пример расчета дистанции
        printf("123");
        printf("%f, %f\n", towers[i].LAT, towers[i].LONG);
        printf("%f, %f, %f\n", coord_towers[i].x, coord_towers[i].y, coord_towers[i].r);
    }

    struct Location location;

    trilateration(coord_towers, towerCount, &location.latitude, &location.longitude);

/*
    if (totalWeight > 0) {
        location.latitude = totalY / totalWeight;
        location.longitude = totalX / totalWeight;
    } else {
        location.latitude = 0;
        location.longitude = 0;
    }*/

    return location;
}

int main() {
    // Открываем файл для логгирования
    FILE *log_file = fopen(LOG_FILE, "a");
    if (log_file == NULL) {
        perror("Ошибка открытия файла логов");
        exit(EXIT_FAILURE);
    }

    // Создаем серверный сокет для приема данных от main_process
    int server_socket = socket(AF_UNIX, SOCK_STREAM, 0);
    if (server_socket == -1) {
        perror("Ошибка создания сокета");
        fclose(log_file);
        exit(EXIT_FAILURE);
    }

    struct sockaddr_un addr;
    memset(&addr, 0, sizeof(addr));
    addr.sun_family = AF_UNIX;
    strncpy(addr.sun_path, DISPLAY_SOCKET_PATH, sizeof(addr.sun_path) - 1);
    unlink(DISPLAY_SOCKET_PATH);

    if (bind(server_socket, (struct sockaddr *)&addr, sizeof(addr)) == -1) {
        perror("Ошибка привязки сокета");
        close(server_socket);
        fclose(log_file);
        exit(EXIT_FAILURE);
    }

    if (listen(server_socket, 5) == -1) {
        perror("Ошибка прослушивания сокета");
        close(server_socket);
        fclose(log_file);
        exit(EXIT_FAILURE);
    }

    printf("Console Display: Ожидание соединений...\n");

    while (1) {
        int client_socket = accept(server_socket, NULL, NULL);
        if (client_socket == -1) {
            perror("Ошибка принятия соединения");
            continue;
        }

        printf("Console Display: Соединение установлено.\n");

        tower_info_t towers[DISPLAY_COUNT] = {0};
        int index = 0;

        while (1) {
            tower_info_t received_msg;
            ssize_t bytes_received = recv(client_socket, &received_msg, sizeof(received_msg), 0);
            if (bytes_received == -1) {
                perror("Ошибка приема данных");
                break;
            } else if (bytes_received == 0) {
                // Клиент закрыл соединение
                printf("Console Display: Клиент закрыл соединение.\n");
                break;
            }

            // Вывод при получении сообщения
            printf("Получено сообщение: msg_type=%ld\n", received_msg.msg_type);

            if (received_msg.msg_type == 1) {  // Получение данных о вышке
                towers[index] = received_msg;

                // Вывод полученных данных о вышке
                printf("Получены данные о вышке: MCC=%d, MNC=%d, CID=%u, Уровень сигнала=%d, LAT=%.6f, LONG=%.6f\n",
                       received_msg.MCC, received_msg.MNC, received_msg.CID,
                       received_msg.receive_level, received_msg.LAT, received_msg.LONG);

                index = (index + 1) % DISPLAY_COUNT;  // Заполняем массив циклически
            } else if (received_msg.msg_type == 2) {  // Сигнал окончания передачи
                printf("\nПередача завершена. Данные о вышках:\n");
                for (int i = 0; i < DISPLAY_COUNT; i++) {
                    if (towers[i].receive_level != 0) {  // Только непустые элементы
                        printf("Вышка %d: MCC=%d, MNC=%d, CID=%u, Уровень сигнала=%d, LAT=%.6f, LONG=%.6f\n",
                               i + 1, towers[i].MCC, towers[i].MNC, towers[i].CID,
                               towers[i].receive_level, towers[i].LAT, towers[i].LONG);

                        // Логгирование координат вышек
                        fprintf(log_file, "Вышка %d: MCC=%d, MNC=%d, CID=%u, Уровень сигнала=%d, LAT=%.6f, LONG=%.6f\n",
                                i + 1, towers[i].MCC, towers[i].MNC, towers[i].CID,
                                towers[i].receive_level, towers[i].LAT, towers[i].LONG);
                    }
                }
                fflush(stdout);

                // Выполнение трилатерации
                struct Location device_location = trilaterate(towers, DISPLAY_COUNT);
                printf("\nРассчитанное местоположение устройства: LAT=%.6f, LONG=%.6f\n",
                       device_location.latitude, device_location.longitude);

                // Логгирование итоговых координат
                fprintf(log_file, "Рассчитанное местоположение устройства: LAT=%.6f, LONG=%.6f\n",
                        device_location.latitude, device_location.longitude);

                // Обновление массива locationHistory
                update_location_history(device_location);

                // Вывод истории местоположений
                printf("\nИстория местоположений:\n");
                for (int i = 0; i < LOCATION_HISTORY_SIZE; i++) {
                    if (locationHistory[i].latitude != 0 || locationHistory[i].longitude != 0) {  // Только непустые координаты
                        printf("Местоположение %d: LAT=%.6f, LONG=%.6f\n", i + 1,
                               locationHistory[i].latitude, locationHistory[i].longitude);
                    }
                }
                fflush(stdout);

                // Очистка массива towers для следующей передачи данных
                memset(towers, 0, sizeof(towers));
                index = 0;

                // Сбросить буфер логов на диск
                fflush(log_file);
            } else {
                printf("Получено неизвестное сообщение с msg_type=%ld\n", received_msg.msg_type);
            }
        }

        close(client_socket);
    }

    // Закрываем файл логов
    fclose(log_file);

    close(server_socket);
    unlink(DISPLAY_SOCKET_PATH);
    return 0;
}
