# PLP

As of June 16, this repository is still being populated.

## About

This is the source repository for 
"PLP - An introduction to mathematical proof"
a [free](https://creativecommons.org/licenses/by-nc-sa/4.0/) web- and pdf- textbook for a first undergraduate course in mathematical proof. 

It is written by [Seckin Demirbas](https://personal.math.ubc.ca/~s.demirbas/) & [Andrew Rechnitzer](https://personal.math.ubc.ca/~andrewr/front_page.html). A very large fraction of the exercises and solutions were contributed by  [Hannah Kohut](https://www.math.ubc.ca/user/2920) and [Charlotte Trainor](https://www.math.ubc.ca/user/2576) with funding from UBC's [OER fund](https://oerfund.open.ubc.ca/) and also the [Mathematics Department](https://www.math.ubc.ca/).

The text grew out of our lecture notes for [Mathematics 220](https://www.calendar.ubc.ca/vancouver/courses.cfm?page=code&code=MATH#220) at UBC. Those notes were written in LaTeX but as we started to transform them into this text we translated them into [PreTeXt](https://pretextbook.org/). Many thanks to [Rob Beezer](http://buzzard.ups.edu/) and the [pretext community](https://groups.google.com/g/pretext-support) for all their help along the way.



## Build instructions

The source is writen in [PreTeXt](https://pretextbook.org/) and so can
be compiled into a number of different formats using the
[pretext-cli](https://pretextbook.org/doc/guide/html/processing-CLI.html).

### Installing PreTeXt CLI
* Requires an up to date `python` installation.
* See instructions at the [pretext-cli repository](https://github.com/PreTeXtBook/pretext-cli/)

### Compile into HTML
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


### Compile into LaTeX and PDF
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
