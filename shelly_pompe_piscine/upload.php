<?php
$target_dir = "uploads/";
$target_file = $target_dir . basename($_FILES["fileToUpload"]["name"]);

if (move_uploaded_file($_FILES["fileToUpload"]["tmp_name"], $target_file)) {
    echo json_encode(["status" => "success", "path" => $target_file]);
} else {
    echo json_encode(["status" => "error", "message" => "Upload failed"]);
}
?>