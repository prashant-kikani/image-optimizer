# image-optimizer
Optimize any image by chroma subsampling and optimized huffman coding.<br/>

## Introduction
Images we capture today, contains so much extra information that is not needed. <br/>
And also our human eye have some limitations. <br/>
So, removing what our eyes can't see is the basic idea. <br/>
Our eye is high sensitive to 'luma' than 'chroma'. So, according to that, image can be optimized.<br/>

## Advantage
The biggest advantage is <b>image resolution is not changed</b> during this optimization process.<br/>
Means if at first image is of size 1458 x 2592, then after optimization process, image resolution will be same 1458 x 2592.<br/>
But image size will be decresed or will remain same (if already optimized).<br/>


## Setup
#### Frameworks and Packages
Make sure you have the following is installed:
 - [Python 3](https://www.python.org/)
 - [NumPy](http://www.numpy.org/)
 - [SciPy](https://www.scipy.org/)
 - PIL (Python Image Library)

## Usage
Give image path by command line argument.<br/>
`
python optimizer.py IMAGE_PATH
`
<br/><br/>
Give relative image path inplace of IMAGE_PATH

## Sample performance
 - Before <b>size 1482 KB</b><br/>
 <p align="center"><img src="imgs/m2.jpg" alt="befimg1" height="500"/></p>
 <br/>
 after <b>size 396 KB</b><br/>
 <p align="center"><img src="imgs/m2_opti_by_pkikani.jpg" alt="befimg1" height="500"/></p>
