/**
 * Image uploader UI
 */

// --- Main functions ----------------------------------------------------------

var Uploader = {};

Uploader.init = function () {
	if (Dropzone && Dropzone.instances[0]) {
		// adjust some settings on Dropzone instance
		Dropzone.instances[0].options.addRemoveLinks        = true; // gives option to remove files from queue
		Dropzone.instances[0].options.acceptedFiles         = 'image/jpeg'; // MIME type
		Dropzone.instances[0].options.parallelUploads       = 1;    // requests active at the same time
		Dropzone.instances[0].options.maxFilesize           = 20;   // in MB
		Dropzone.instances[0].options.resizeHeight          = 800;  // resize to given height in pixels
		Dropzone.instances[0].options.resizeQuality         = 1;    // in range 0..1 (default 0.8)

		// set events on Dropzone instance
		Dropzone.instances[0].on("success", function (file) {
			Uploader.onUploadSuccess();
		});
		Dropzone.instances[0].on("complete", function (file) {
			if (file.upload.progress == 100) {
				this.removeFile(file);
			}
			// else something has gone wrong
		});
	}

	// get elements
	Uploader.uploadCounter         = 0;
	Uploader.uploadCounterFeedback = document.getElementById('upload_counter')
	Uploader.dropNotification      = document.getElementById('drop_notification');

	// set styles
	Uploader.dropNotification.style.display = 'none';

	// set event listeners
	window.addEventListener('dragover',  Uploader.onSourceFileDrag, false);
    window.addEventListener('dragenter', Uploader.onSourceFileDrag, false);
    window.addEventListener('dragleave', Uploader.onSourceFileDrag, false);
    window.addEventListener('dragend',   Uploader.onSourceFileDrag, false);
	window.addEventListener('drop',      Uploader.onSourceFileDrop, false);
};

Uploader.onUploadSuccess = function () {
	Uploader.uploadCounter++;
	Uploader.uploadCounterFeedback.innerHTML = Uploader.uploadCounter + ' already done!';
};

Uploader.onSourceFileDrag = function (inEvent) {
	// dragover, dragenter need to return false for a valid drop target element
	if (inEvent.type === 'dragleave' || inEvent.type === 'dragend') {
		Uploader.dropNotification.style.display = 'none';
	} else {
		Uploader.dropNotification.style.display = '';
	}
	inEvent.preventDefault();
};

Uploader.onSourceFileDrop = function (inEvent) {
	//var files = (inEvent && inEvent.dataTransfer) ? inEvent.dataTransfer.files : undefined;

	// pass on event to Dropzone.JS element for proper handling
	if (Dropzone && Dropzone.instances[0]) {
		Dropzone.instances[0].drop(inEvent);
	}

	// reset looks
	Uploader.dropNotification.style.display = 'none';
	// prevent setting page url to this file location
	inEvent.preventDefault();
};

// --- Initialise --------------------------------------------------------------

/**
 * Wait for whole page to load before setting up.
 * Prevents problems with objects not loaded yet while trying to assign these.
 */
window.addEventListener('pageshow', function () {
	Uploader.init();
}, false);