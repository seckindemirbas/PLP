# Sources for the PLP book

## Files

The source files for the book have been arranged to be compatible with the [pretext-cli](https://pretextbook.org/doc/guide/html/processing-CLI.html). Accordingly
* the actual book sources lie inside the `source` subdirectory.
  * the main file is called `plp.ptx` which pulls in the other files.
  * `docinfo` contains misc latex commands and some pretext options
  * `fontmatter` contains acknowledgements, dedications, etc
  * `backmatter` contains some pretext instructions about exercise hints and solutions.
  * the chapters of the text are in the `source/text` subdirectory
  * the exercises are in the `source/problems` subdirectory and sub-subdirectories for each chapter. Each exercise is a single file.
* the [publication.ptx](https://pretextbook.org/doc/guide/html/publication-file.html) and [project.ptx](https://pretextbook.org/doc/guide/html/cli-publication.html) files are required by pretext to compile the source.
* svg and pdf image files reside in the `assets` subdirectory. The svg images were drawn using [inkscape](https://inkscape.org/) and then converted to pdf.




## Compile into HTML
* From the repository root directory move into the `plp_book` subdirectory
```
$ cd book
```
* Then run
```
$ pretext build html
```
* This will take a little time - roughly 3 minutes on a modest linux laptop computer
* The resulting HTML will be produced in the `output/html` subdirectory
* To view the HTML run
```
$ pretext view html
```
* This launches a mini http-server. It should tell you something like 
```
PreTeXt project found in `<PATH TO THE REPOSITORY>/PLP/plp_book`.
Now starting a server to preview directory `<PATH TO THE REPOSITORY>/PLP/plp_book/output/html`.

Success! Open the below url in a web browser to preview the most recent build of your project.
    http://localhost:8000
Use [Ctrl]+[C] to halt the server.

```
* Open your browser to the indicated URL to view the text.
* You can also easily copy the site to a webserver by (for example)
```
$ cd output/
$ tar -zcf html.tar.gz html
```
This produces a gzip'd tar file of the HTML. Copy that to the desired location and then untar it using
```
$ tar -zxf html.tgz
```
Then rename the `html` directory to whatever you like.


## Compile into LaTeX and PDF
* From the repository root directory move into the `plp_book` subdirectory
```
$ cd book
```
* Then run
```
$ pretext build latex 
```
$ pretext build latex --stringparam latex.font.size 12pt
```
for a slightly larger font.
* This will take a little time - roughly 8 minutes on a modest linux laptop computer
* The latex is output to the `output/latex` subdirectory
* To then compile this latex into PDF run 
```
pdflatex main.tex
```
or
```
latexmk main.tex
```
This latter command takes about 30s on a modest laptop.


Sources for the PLP text and exercises here. Files arranged in format compatible with the pretext-cli.
