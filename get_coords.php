<?php

use PDO;

function load_env($path = '.env') {
    if (!file_exists($path)) {
        throw new Exception(".env file not found.");
    }

    $lines = file($path, FILE_IGNORE_NEW_LINES | FILE_SKIP_EMPTY_LINES);
    foreach ($lines as $line) {
        if (strpos(trim($line), '#') === 0) {
            continue;
        }

        list($name, $value) = explode('=', $line, 2);
        $name = trim($name);
        $value = trim($value);

        if (!array_key_exists($name, $_ENV) && !array_key_exists($name, $_SERVER)) {
            putenv("$name=$value");
            $_ENV[$name] = $value;
            $_SERVER[$name] = $value;
        }
    }
}

load_env(__DIR__ . '/.env');

// Путь к файлу с данными
$file_path = getenv('PATH_TO_LOG');

// Проверка наличия файла
if (!file_exists($file_path)) {
    echo json_encode(["error" => "Файл не найден"]);
    exit;
}

// Чтение файла и получение всех строк
$lines = file($file_path, FILE_IGNORE_NEW_LINES | FILE_SKIP_EMPTY_LINES);

// Создаем массив для вышек и координат устройства
$cell_towers = [];
$device_location = null;

// Парсим строки
foreach ($lines as $line) {
    // Ищем вышки по шаблону "MCC=..., MNC=..., CID=..., Уровень сигнала=..., LAT=..., LONG=..."
    if (preg_match('/MCC=(\d+), MNC=(\d+), CID=(\d+), Уровень сигнала=(\d+), LAT=([\d.]+), LONG=([\d.]+)/', $line, $matches)) {
        $cell_towers[] = [
            'CID' => (int)$matches[3],
            'Signal' => (int)$matches[4],
            'lat' => (float)$matches[5],
            'lon' => (float)$matches[6],
        ];
    }
    // Проверяем строку на координаты устройства
    elseif (preg_match('/Рассчитанное местоположение устройства: LAT=([\d.]+), LONG=([\d.]+)/', $line, $matches)) {
        $device_location = [
            'lat' => (float)$matches[1],
            'lon' => (float)$matches[2],
        ];
    }
}

// Формируем JSON-ответ
$response = [
    "device_location" => $device_location ?: ["error" => "Не удалось найти рассчитанное местоположение устройства"],
    "towers" => $cell_towers
];

echo json_encode($response, JSON_UNESCAPED_UNICODE | JSON_PRETTY_PRINT);
