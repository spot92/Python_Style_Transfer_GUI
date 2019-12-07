# Python_Style_Transfer_GUI
Took the neural style transfer for python and made it way more user friendly.

## Background
This was made with Python 3.7.4 on a Windows 10 machine.

I take the style transfer code from this repo and turn it into a more user friendly experience:
https://github.com/spot92/neural-style-pt

This is just a fork of the following with some minor changes to the image sizing:
https://github.com/ProGamerGov/neural-style-pt

And this is a Python implementation of the Lua code here:
https://github.com/jcjohnson/neural-style

## Requirements
For any of the requirements, such as torch, scipy, etc., I will refer you to the ProGamerGov repo as it has basically everything you could want there.

In addition to all of those python packages, you will need to run the following:
pip install gooey

You will need a CUDA capable graphics card (which I believe is NVidia only) in order to run this with any sort of reasonable speed. I have never run this on CPU myself, but my understanding is that it is significantly slower.

And again, to be clear, this is just the GUI file for this. If you would like to get the CaffeLoader.py file or the models folder, I will direct you to https://github.com/spot92/neural-style-pt or https://github.com/ProGamerGov/neural-style-pt (The ProGamerGov one is much more actively maintained and I would defer to that for these files).

NOTE: YOU DO NOT NEED THE neural_style.py OR neural_style_my_edits.py FILES FOR THIS TO WORK.

Once you have gotten set up with the necessary files and models from the other repos, come back here.
Make sure that all the files and models are in the same root folder. For example, my folder is D:/Neural Style Python and I have every other necessary folder/file in there. I find it helpful to have separate folders for content, styles, and output, but this is not required.

## Running It
This is what it should look like when run sucessfully:

![Image of Interface](https://github.com/spot92/Python_Style_Transfer_GUI/blob/master/interface.jpg)
