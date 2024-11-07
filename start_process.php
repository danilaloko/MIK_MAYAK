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

$path_to_sim_exe = getenv('PATH_TO_SIM_EXE');
$path_to_db_exe = getenv('PATH_TO_DB_EXE');
$path_to_calc_exe = getenv('PATH_TO_CALC_EXE');

// Путь к JSON-файлу для хранения PID
$jsonFilePath = __DIR__ . '/process_info.json';

// Функция для записи PIDs в JSON-файл
function savePidsToJson($pids) {
    global $jsonFilePath;
    $data = ['PIDs' => $pids];
    file_put_contents($jsonFilePath, json_encode($data));
}

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
    $pid = (int)$pid;
    if ($pid <= 0) {
        return false;
    }
    $status = shell_exec("ps -p $pid");
    if (strpos($status, (string)$pid) !== false) {
        return true;
    }
    return false;
}

// Функция для запуска процесса и получения его PID
function startProcess($command) {
    // Запускаем процесс в фоне
    $command = "nohup $command > /dev/null 2>&1 & echo $!";
    $output = [];
    exec($command, $output);
    $pid = (int)$output[0];
    return $pid;
}

// Проверка метода запроса
if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    $pids = getPidsFromJson();

    // Запускаем процессы в порядке CALC, DB, SIM
    $processes = [
        'CALC' => $path_to_calc_exe,
        'DB' => $path_to_db_exe,
        'SIM' => $path_to_sim_exe
    ];

    $responses = [];

    foreach ($processes as $key => $exePath) {
        $pid = $pids[$key] ?? null;

        if ($pid && isProcessRunning($pid)) {
            // Если процесс уже работает
            $responses[$key] = ['status' => 'error', 'message' => "Процесс $key уже запущен", 'pid' => $pid];
        } else {
            // Запускаем процесс
            $pid = startProcess($exePath);

            // Проверяем, работает ли процесс
            if (isProcessRunning($pid)) {
                // Сохраняем PID
                $pids[$key] = $pid;
                $responses[$key] = ['status' => 'success', 'message' => "Процесс $key успешно запущен", 'pid' => $pid];
            } else {
                // Процесс не запустился или завершился сразу
                $responses[$key] = ['status' => 'error', 'message' => "Не удалось запустить процесс $key"];
            }
        }

    }

    // Сохраняем все PID в JSON-файл
    savePidsToJson($pids);

    // Возвращаем ответ
    header('Content-Type: application/json');
    echo json_encode($responses);
}
