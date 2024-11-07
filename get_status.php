<?php

// Путь к JSON-файлу для хранения PID
$jsonFilePath = __DIR__ . '/process_info.json';

// Функция для получения PIDs из JSON-файла
function getPidsFromJson() {
    global $jsonFilePath;
    if (file_exists($jsonFilePath)) {
        $data = json_decode(file_get_contents($jsonFilePath), true);
        return $data['PIDs'] ?? [];
    }
    return [];
}

// Функция для проверки, работает ли процесс
function isProcessRunning($pid) {
    $status = shell_exec("ps -p $pid");
    if ($pid && strpos($status, (string)$pid) !== false) {
        return true;
    }
    return false;
}

// Проверка метода запроса
if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    $pids = getPidsFromJson();
    $statuses = [];

    foreach ($pids as $processName => $pid) {
        if (isProcessRunning($pid)) {
            $statuses[$processName] = ['status' => 'running', 'pid' => $pid];
        } else {
            $statuses[$processName] = ['status' => 'stopped', 'pid' => $pid];
        }
    }

    header('Content-Type: application/json');
    echo json_encode($statuses);
}
