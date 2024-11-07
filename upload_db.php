<?php
use PDO;

$allowedFormats = ['csv', 'db'];

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

$uploadDir = getenv('PATH_TO_DB');
$db_name = getenv('DB_NAME');
$path_to_exe = getenv('PATH_TO_EXE');
$path_to_log = getenv('PATH_TO_LOG');

if ($_SERVER['REQUEST_METHOD'] === 'POST' && isset($_FILES['db'])) {
    $file = $_FILES['db'];
    
    // Получаем расширение файла
    $fileExtension = strtolower(pathinfo($file['name'], PATHINFO_EXTENSION));
    
    if (!in_array($fileExtension, $allowedFormats)) {
        http_response_code(500);
        echo 'Недопустимый формат файла.';
        exit;
    }

    if (!is_dir($uploadDir)) {
        mkdir($uploadDir, 0777, true);
    }
    $uploadPath = $uploadDir . '/' . $db_name . '.' . $fileExtension;

    if (move_uploaded_file($file['tmp_name'], $uploadPath)) {
        echo "200";
        exit;
    } else {
        http_response_code(500);
        exit;
    }
}
