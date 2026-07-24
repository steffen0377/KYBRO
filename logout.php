<?php
$incl = [
   '/includes/auth.php',
   '/includes/functions.php'
];
foreach ($incl as $datei) {
    require_once __DIR__ . $datei;
}
logout();
redirect('login.php');
