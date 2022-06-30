# Sources for PLP slides

## Files
* The slides are arranged into 43 separate files, roughly topic-by-topic.
* Each slide-show is called `topic_XX.ptx` and is self-contained.
* The png images lie in the `figure` subdirectory. Those PNG were created from the svg files used in the book; the conversion was done using [inkscape](https://inkscape.org/).
* we give the html-output as `topic_XX.html` and the associated PDF rendering as `pdf_out/topic_XX.pdf`

## Compile to HTML / reveal.js
* At this time the [pretext-cli](https://pretextbook.org/doc/guide/html/processing-CLI.html) does not (officially) support compiling slides, however our build process does still depend on having a working pretext-cli installation.
* The `build_slides.py` python3 script will compile a single file. Run it as
```
python build_slides.py topic_17.ptx
```
You may need to run this with `python3` depending on your python installation.
* That will produce a `topic_17.html` file which is a reveal.js presentation. It does not require a reveal.js installation, but does expect a working internet connection to obtain various css and js files.
* The `build_all_slides.py` file is a simple wrapper around the `build_slides.py` file that builds all 43 slideshows. To run it
```
python build_all_slides.py
```

## Compiling HTML to PDF
* Reveal.js does have an option to export to pdf - see [here](https://revealjs.com/pdf-export/)
* Otherwise we have used [decktape](https://github.com/astefanutti/decktape).
* The `build_slides.py` script can be modified to also produce pdf output. Around line 65 of the script there is a `quit()`; commenting out that command will allow the rest of the script to run and produce pdf output.