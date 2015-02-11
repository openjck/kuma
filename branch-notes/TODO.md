* Download the texzilla, youtube, and tablesort rather than having them
  source-controlled. There is a Bower package for the youtube plugin, but it's
  for a newer version. The files are also organized differently than other
  CKEditor Bower packages
* Handle any CKEditor assets (or CKEditor plugin assets) that are referenced
  directly in templates
* Revision any CKE assets that are currently cache-bust with BUILD_ID_JS
* Determine thet ckeditor-dev revision hash automatically when the java command
  is called
* Update the plugin paths in kuma/wiki/templates/wiki/includes/ckeditor_scripts.html
