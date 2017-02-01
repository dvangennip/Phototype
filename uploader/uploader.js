/**
 * Image uploader UI
 */

// --- Main functions ----------------------------------------------------------

var Uploader = {};

Uploader.init = function () {
	Uploader.dropNotification = document.getElementById('drop_notification');

	// set styles
	Uploader.dropNotification.style.display = 'none';

	// set event listeners
	window.addEventListener('dragover',  Uploader.onSourceFileDrag, false);
    window.addEventListener('dragenter', Uploader.onSourceFileDrag, false);
    window.addEventListener('dragleave', Uploader.onSourceFileDrag, false);
    window.addEventListener('dragend',   Uploader.onSourceFileDrag, false);
	window.addEventListener('drop',      Uploader.onSourceFileDrop, false);
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