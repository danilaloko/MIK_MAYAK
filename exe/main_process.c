// main_process.c
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <signal.h>
#include <stdarg.h>
#include <time.h>
#include <errno.h>
#include <sys/socket.h>
#include <sys/un.h>
#include "hashutils.h"
#include "msg_definitions.h"

#define SOCKET_PATH "/tmp/gsm_socket"
#define DISPLAY_SOCKET_PATH "/tmp/display_socket"

struct display_message {
    long msg_type;
    uint16_t MCC;
    uint16_t MNC;
    uint32_t CID;
    int receive_level;
    float LAT;
    float LONG;
};

size_t DBSIZE;
FILE *log_file = NULL;

// Функция для логирования сообщений
void log_message(const char *format, ...) {
    if (log_file == NULL) return;

    va_list args;
    va_start(args, format);

    // Получаем текущее время
    time_t now = time(NULL);
    char timestr[20];
    struct tm *tm_info = localtime(&now);
    strftime(timestr, sizeof(timestr), "%Y-%m-%d %H:%M:%S", tm_info);

    fprintf(log_file, "[%s] ", timestr);
    vfprintf(log_file, format, args);
    fprintf(log_file, "\n");
    fflush(log_file);

    va_end(args);
}

// Функция для логирования ошибок
void log_error(const char *msg) {
    if (log_file == NULL) return;
    int errnum = errno;
    time_t now = time(NULL);
    char timestr[20];
    struct tm *tm_info = localtime(&now);
    strftime(timestr, sizeof(timestr), "%Y-%m-%d %H:%M:%S", tm_info);

    fprintf(log_file, "[%s] ERROR: %s: %s\n", timestr, msg, strerror(errnum));
    fflush(log_file);
}

// Обработчик сигналов для логирования аварийных завершений
void signal_handler(int sig) {
    log_message("Caught signal %d (%s), terminating gracefully.", sig, strsignal(sig));
    if (log_file) {
        fclose(log_file);
    }
    exit(EXIT_FAILURE);
}

int main() {
    // Установка обработчиков сигналов
    signal(SIGSEGV, signal_handler);
    signal(SIGABRT, signal_handler);
    signal(SIGINT, signal_handler);
    signal(SIGTERM, signal_handler);
    signal(SIGPIPE, SIG_IGN);  // Игнорируем SIGPIPE

    // Открываем файл для логирования
    log_file = fopen("main_process.log", "a");
    if (log_file == NULL) {
        fprintf(stderr, "Failed to open log file: %s\n", strerror(errno));
        // Продолжаем работу без логирования
    }

    char *file = "250.csv";
    DBSIZE = count_db_lines(file);
    struct Node **hash_table = (struct Node **)calloc(DBSIZE, sizeof(struct Node));
    if (!hash_table) {
        log_error("Failed to allocate memory for hash table");
        if (log_file) fclose(log_file);
        exit(EXIT_FAILURE);
    }
    parse_and_insert_db(file, hash_table);
    log_message("Hash table created and waiting for requests...");

    // Создаем серверный сокет для приема данных
    int server_socket = socket(AF_UNIX, SOCK_STREAM, 0);
    if (server_socket == -1) {
        log_error("Socket creation failed");
        free(hash_table);
        if (log_file) fclose(log_file);
        exit(EXIT_FAILURE);
    }
    log_message("Server socket created.");

    struct sockaddr_un addr;
    memset(&addr, 0, sizeof(addr));
    addr.sun_family = AF_UNIX;
    strncpy(addr.sun_path, SOCKET_PATH, sizeof(addr.sun_path) - 1);
    unlink(SOCKET_PATH);

    if (bind(server_socket, (struct sockaddr *)&addr, sizeof(addr)) == -1) {
        log_error("Bind failed");
        close(server_socket);
        free(hash_table);
        if (log_file) fclose(log_file);
        exit(EXIT_FAILURE);
    }
    log_message("Server socket bound to %s.", SOCKET_PATH);

    if (listen(server_socket, 5) == -1) {
        log_error("Listen failed");
        close(server_socket);
        free(hash_table);
        if (log_file) fclose(log_file);
        exit(EXIT_FAILURE);
    }
    log_message("Server socket is listening.");

    // Создаем клиентский сокет для отправки данных в display
    int display_socket = socket(AF_UNIX, SOCK_STREAM, 0);
    if (display_socket == -1) {
        log_error("Failed to create display socket");
        free(hash_table);
        close(server_socket);
        if (log_file) fclose(log_file);
        exit(EXIT_FAILURE);
    }
    log_message("Display socket created.");

    struct sockaddr_un display_addr;
    memset(&display_addr, 0, sizeof(display_addr));
    display_addr.sun_family = AF_UNIX;
    strncpy(display_addr.sun_path, DISPLAY_SOCKET_PATH, sizeof(display_addr.sun_path) - 1);

    // Подключаемся к display сокету
    int connect_attempts = 0;
    while (connect(display_socket, (struct sockaddr *)&display_addr, sizeof(display_addr)) == -1) {
        if (connect_attempts >= 5) {
            log_error("Failed to connect to display socket after multiple attempts");
            free(hash_table);
            close(server_socket);
            close(display_socket);
            if (log_file) fclose(log_file);
            exit(EXIT_FAILURE);
        }
        log_error("Failed to connect to display socket, retrying in 1 second");
        sleep(1);
        connect_attempts++;
    }
    log_message("Connected to display socket at %s.", DISPLAY_SOCKET_PATH);

    while (1) {
        int client_socket = accept(server_socket, NULL, NULL);
        if (client_socket == -1) {
            log_error("Accept failed");
            continue;
        }

        log_message("Accepted connection from gsm_read");

        while (1) {
            struct {
                uint8_t tower_count;
                struct {
                    uint16_t MCC;
                    uint16_t MNC;
                    uint32_t CID;
                    int receive_level;
                } tower_data[7];
            } level_data_packet;

            ssize_t bytes_received = recv(client_socket, &level_data_packet, sizeof(level_data_packet), 0);
            if (bytes_received == -1) {
                log_error("Receive failed");
                break;
            } else if (bytes_received == 0) {
                // Клиент завершил соединение
                log_message("gsm_read closed the connection");
                break;
            }

            log_message("Received data packet with %d towers", level_data_packet.tower_count);

            // Обработка каждой вышки
            for (int i = 0; i < level_data_packet.tower_count; i++) {
                uint16_t MCC = level_data_packet.tower_data[i].MCC;
                uint16_t MNC = level_data_packet.tower_data[i].MNC;
                uint32_t CID = level_data_packet.tower_data[i].CID;
                int receive_level = level_data_packet.tower_data[i].receive_level;

                log_message("Processing tower %d: MCC=%d, MNC=%d, CID=%u, receive_level=%d",
                            i + 1, MCC, MNC, CID, receive_level);

                struct Node *result = search_in_hash_table(hash_table, MCC, MNC, CID);
                if (result) {
                    log_message("Found tower in hash table: LAT=%.6f, LONG=%.6f", result->LAT, result->LONG);
                } else {
                    log_message("Tower not found in hash table. Setting LAT and LONG to 0.0");
                }

                struct display_message msg = {
                    .msg_type = 1,
                    .MCC = MCC,
                    .MNC = MNC,
                    .CID = CID,
                    .receive_level = receive_level,
                    .LAT = result ? result->LAT : 0.0,
                    .LONG = result ? result->LONG : 0.0
                };

                // Отправка данных в display через сокет
                ssize_t bytes_sent = send(display_socket, &msg, sizeof(msg), 0);
                if (bytes_sent == -1) {
                    log_error("Failed to send data to display");
                    // Проверяем, если ошибка - сломано соединение
                    if (errno == EPIPE) {
                        log_error("Broken pipe detected, attempting to reconnect to display socket");
                        close(display_socket);
                        // Повторное подключение к display сокету
                        display_socket = socket(AF_UNIX, SOCK_STREAM, 0);
                        if (display_socket == -1) {
                            log_error("Failed to recreate display socket");
                            break;
                        }
                        connect_attempts = 0;
                        while (connect(display_socket, (struct sockaddr *)&display_addr, sizeof(display_addr)) == -1) {
                            if (connect_attempts >= 5) {
                                log_error("Failed to reconnect to display socket after multiple attempts");
                                break;
                            }
                            log_error("Failed to reconnect to display socket, retrying in 1 second");
                            sleep(1);
                            connect_attempts++;
                        }
                        if (connect_attempts >= 5) {
                            // Не удалось восстановить соединение
                            break;
                        }
                        log_message("Reconnected to display socket at %s.", DISPLAY_SOCKET_PATH);
                        // Повторяем отправку данных
                        bytes_sent = send(display_socket, &msg, sizeof(msg), 0);
                        if (bytes_sent == -1) {
                            log_error("Failed to resend data to display after reconnection");
                            break;
                        } else {
                            log_message("Resent data to display after reconnection: LAT=%.6f, LONG=%.6f", msg.LAT, msg.LONG);
                        }
                    } else {
                        break;
                    }
                } else {
                    log_message("Sent to display: LAT=%.6f, LONG=%.6f", msg.LAT, msg.LONG);
                }
            }

            // Отправка сигнала окончания передачи
            struct display_message end_msg = {.msg_type = 2};
            ssize_t bytes_sent = send(display_socket, &end_msg, sizeof(end_msg), 0);
            if (bytes_sent == -1) {
                log_error("Failed to send end message to display");
            } else {
                log_message("Sent end message to display");
            }
        }

        close(client_socket);
        log_message("Closed connection with gsm_read");
    }

    // Закрываем сокеты и освобождаем ресурсы
    log_message("Shutting down server");
    close(display_socket);
    free(hash_table);
    close(server_socket);
    unlink(SOCKET_PATH);
    if (log_file) {
        fclose(log_file);
    }
    return 0;
}
