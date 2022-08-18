# PLP 

## About

This is the source repository for 
"PLP - An introduction to mathematical proof"
a [free](https://creativecommons.org/licenses/by-nc-sa/4.0/) web- and pdf- textbook for a first undergraduate course in mathematical proof. You can find the book (as both html and pdf) and slides on the [main textbook website](https://www.math.ubc.ca/~PLP).


It is written by [Seckin Demirbas](https://personal.math.ubc.ca/~s.demirbas/) & [Andrew Rechnitzer](https://personal.math.ubc.ca/~andrewr/front_page.html). A very large fraction of the exercises and solutions were contributed by  [Hannah Kohut](https://www.math.ubc.ca/user/2920) and [Charlotte Trainor](https://www.math.ubc.ca/user/2576) with funding from UBC's [OER fund](https://oerfund.open.ubc.ca/) and also the [Mathematics Department](https://www.math.ubc.ca/).

The text grew out of our lecture notes for [Mathematics 220](https://www.calendar.ubc.ca/vancouver/courses.cfm?page=code&code=MATH#220) at UBC. Those notes were written in LaTeX but as we started to transform them into this text we translated them into [PreTeXt](https://pretextbook.org/). Many thanks to [Rob Beezer](http://buzzard.ups.edu/) and the [pretext community](https://groups.google.com/g/pretext-support) for all their help along the way.

The repository contains sources for the textbook and also lecture slides. The slides should be considered ancillary materials and were used to produce [short online videos](https://www.youtube.com/playlist?list=PLsZ5tCZabvkCNItGgafhVqzekTwEbHyYk) for Mathematics 220 at UBC. 

We have also added worksheets used to teach a 13 week course from PLP.



## Building
The sources for both the book and lecture are written in [PreTeXt](https://pretextbook.org/).
* The book can be compiled into multiple different formats using the [pretext-cli](https://pretextbook.org/doc/guide/html/processing-CLI.html).
* The slides compile to [reveal.js](https://revealjs.com/) html presentations, which, in turn, can be rendered as PDFs using tools such as [decktape](https://github.com/astefanutti/decktape).

Build instructions for the book and slides can be found in the relevant subdirectories.

The worksheets are written standard latex and can be compiled using (for example) pdflatex.

### Installing PreTeXt CLI
* Requires an up to date `python` installation.
* See instructions at the [pretext-cli repository](https://github.com/PreTeXtBook/pretext-cli/)

### Installing Reveal.js
* The slides compile so that no reveal.js installation is required.

### Installing decktape
* See [decktape repository](https://github.com/astefanutti/decktape)




