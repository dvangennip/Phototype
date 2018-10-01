<?php
/**
 * data_uploader.php
 *
 * Used in conjunction with photocore.py
 */

 /**
 * Handle an upload field/file.
 * Reject files too big (constant MAX_FILE_SIZE), filter out uploaded file name
 * (remove path, reduce charset, reject incorrect file types (actually, extensions),
 * truncate given name), then prepend unique identifier (date/time, good for sorting)
 * and move the uploaded file to the given directory.
 * Note: destination folders must have permission chmod'ed to 777 to allow writing files there.
 *
 * @param $fieldName   the name of the input type="file" tag in HTML.
 *        There can be several such inputs in a form.
 * @param $destinationDir   where to put the uploaded file (absolute path).
 *        Might be always the same place or depend on other parameters like a login name.
 * @param $allowedExtensions   an array looking like array('.png', '.gif', '.jpg', '.jpeg')
 * @return An array with three elements. If error, the first element is an empty string,
 *         the second one is the error message. Otherwise, the first element is the file name
 *         and the second one is the uploaded file path, with the third the mime type (e.g., image/png)
 */
function handle_uploaded_file ($fieldName, $destinationDir, $destinationPrefix, $allowedExtensions, $allow_overwrite) {
	global $debugData; // To trace actions. Comment out the lines with this variable for real use

    if (isset($_FILES[$fieldName])) {
        // Handle error code
        $error = $_FILES[$fieldName]['error'];
        switch ($error) {
	        case UPLOAD_ERR_OK: // zero
	            break;  // No error, continue process
	        case UPLOAD_ERR_INI_SIZE: // 1
	        case UPLOAD_ERR_FORM_SIZE: // 2
	            return array('', 'File too big!'); // The Web page should indicate upfront the maximum size...
	        case UPLOAD_ERR_PARTIAL: // 3
	            return array('', 'Incomplete upload, please retry.');
	        case UPLOAD_ERR_NO_FILE: // 4
	            return array('', 'No file! Give a file in the upload field...');
	        case UPLOAD_ERR_TMP_DIR: // 6 - No temp folder! :(
	        case UPLOAD_ERR_CANT_WRITE: // 7 - Can't write! chmod error?
	            return array('', 'Bad server config! Sorry...');
	        case UPLOAD_ERR_EXTENSION: // 8 - File upload stopped by extension
	            return array('', 'Bad file extension.');
	        default:    // Future version of PHP?
	            return array('', "Error when uploading: $error");
        }

        // Check size of uploaded file
        $tempLocation = $_FILES[$fieldName]['tmp_name'];
        $debugData[] = "Uploaded file is in: $tempLocation";
        $debugData[] = "Other info given by browser (size, type): {$_FILES[$fieldName]['size']}, {$_FILES[$fieldName]['type']}";
        $fileSize = filesize($tempLocation);
        $debugData[] = "Real file size: $fileSize";
        // Strangely enough, if IE is given a path leading to nowhere, it just sends a 0 byte file!
        if ($fileSize == 0) { // Might test a minimum size (smallest header size for graphics...)
            return array('', 'File is empty!');
        }

        // Get original file name
        $file = $_FILES[$fieldName]['name'];
        $debugData[] = "Original file name: $file"; // No HTML escape! :(
        // Strip out the path (given by IE, perhaps other browsers -- Firefox and Opera just give the name)
        // Most samples I saw use basename() but I found out that it fails to strip a Windows path on a Unix server
        // I could have used a str_replace, but I like REs...
        // (I gobble anything up to the last sequence of characters not having slash or anti-slash in it)
        // Note: ensure magic quotes are disabled or neutralized
        $file = preg_replace('!.*?([^\\/]+)$!', '$1', $file);
        $debugData[] = "Filter 1: $file";
        // Filter out all characters that are not alphanumerical, dot and dash
        // as they can be troublesome in some OSes.
        // A sequence of such chars is replaced by a unique underscore.
        $file = preg_replace('/[^a-zA-Z0-9.-]+/', '_', $file);
        $debugData[] = "Filter 2: $file";
        // Split name and extension: gobble everything up to the last dot (file name), then dot and remainder (extension)
        // Note that .htaccess has no extension and is a pure filename
        if (preg_match('/^(.+)\.([^.]+)$/', $file, $m) == 0) {
            // No match => No dot or nothing before the dot
            $extension = '';
        } else {
            $file = $m[1];
            $extension = $m[2];
        }
        $debugData[] = "Split: $file $extension";
        // If extension not allowed (could be a CGI file...), discard it
        if ($extension != '' && !in_array($extension, $allowedExtensions)) {
            return array('', 'File format not allowed.');
        }

        // Add trailing slash to dest dir, supposed in Unix format
        // (if not slash at end, replace last char by itself followed by a slash)
        $destinationDir = preg_replace('!([^/])$!', '$1/', $destinationDir);

        // a prefix is added to the filename here
        // if numerical but no underscore (e.g., "234_") at the end of the prefix it just takes the prefix as the filename
        if (preg_match("/^\d+$/", $destinationPrefix)) {
        	$destinationFile = $destinationPrefix . ($extension != '' ? '.' . $extension : '');
        } else {
        	$destinationFile = $destinationPrefix . $file . ($extension != '' ? '.' . $extension : '');
        }
        $debugData[] = "Destination file: $destinationFile.";
        $destinationPath = $destinationDir . $destinationFile;
        $debugData[] = "Destination path: $destinationPath.";
        // Move uploaded file from temporary folder to destination
        // Overwrite a file of same name there, if any (unless, perhaps server is on Windows, might just fail to move).
		if (!file_exists($destinationPath) || $allow_overwrite) {
			if (!move_uploaded_file($tempLocation, $destinationPath)) {
				return array('', 'Failed to move uploaded file.: ' . $destinationPath);
			}
            return array($destinationFile, $destinationPath, $_FILES[$fieldName]['type']);
		} else {
			return array('', 'File already exists in: ' . $destinationPath);
		}
    } else {
		return array('', 'Field not found');
    }
    return array($finalName, 'OK');
}

// --- Initialise -------------------------------------------------

//error_reporting(E_ALL);

// initiate variables
$debugData = array();
$error = '';

// request method must be POST
$requestMethod = $_SERVER['REQUEST_METHOD'];
if ($requestMethod != "POST") {
	$error .= ' Request must be done via POST';
}

$destDir = '';
$destPrefix = '';
$allowedExtensions = array('bin', 'log');
$allow_overwrite = 1

// do the actual work if everything is fine so far
if ($error == '') {
	// upload the file from input[type=file] with name 'f'
	$result = handle_uploaded_file('f', $destDir, $destPrefix, $allowedExtensions, $allow_overwrite);
} else $error .= ' No uploading done.';

// give feedback as JSON
$response = '{';
if ($error != '' || $result[0] == '') {
    $response .= '"success": false, "error": "'.$error . $result[1] . '"';
} else {
	$fileURL = 'http://www.sinds1984.nl/' . preg_replace("/\.\.\//", "", $destDir) . '/' . $result[0];
	$response .= '"success": true, "fileLocation": "'.$fileURL.'"';
}
if (count($debugData) != 0) {
	$response .= ', "debug": [';
	for ($i = 0; $i < count($debugData); $i++) {
		if ($i != 0) $response .= ',';
		$response .= '"'.$debugData[$i].'"';
	}
	$response .= ']';
}
$response .= '}';

header('Content-type: application/json; charset=utf-8');
echo $response;

?>