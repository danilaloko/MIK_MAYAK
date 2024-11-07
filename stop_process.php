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

$path_to_exe = getenv('PATH_TO_EXE');
$path_to_log = getenv('PATH_TO_LOG');

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

// Функция для сохранения PIDs в JSON-файл
function savePidsToJson($pids) {
    global $jsonFilePath;
    $data = ['PIDs' => $pids];
    file_put_contents($jsonFilePath, json_encode($data));
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
    $responses = [];

    foreach ($pids as $processName => $pid) {
        if (isProcessRunning($pid)) {
            exec("kill $pid", $output, $return_var);

            if ($return_var === 0) {
                $responses[$processName] = [
                    'status' => 'success',
                    'message' => "Процесс $processName с PID $pid успешно завершён."
                ];
            } else {
                $responses[$processName] = [
                    'status' => 'error',
                    'message' => "Не удалось завершить процесс $processName с PID $pid."
                ];
            }
        } else {
            $responses[$processName] = [
                'status' => 'stopped',
                'message' => "Процесс $processName с PID $pid уже остановлен."
            ];
        }

        // Удаляем процесс из списка независимо от результата
        unset($pids[$processName]);
    }

    // Сохраняем обновлённый список PIDs
    savePidsToJson($pids);

    // Возвращаем ответ
    http_response_code(200);
    header('Content-Type: application/json');
    echo json_encode($responses);
}
