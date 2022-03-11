# Import libraries
from PIL import Image
import sys
from pdf2image import convert_from_path

# Path of the pdf
PDF_file = r"D:\Users\Simon\Python-VSCode\projects\ExamScanner\d.pdf"

'''
Part #1 : Converting PDF to images
Poppler is required by pdf2image. On Windows it is a pain to install. I downloaded a binary and added the poppler_path parameter to the call below.
'''

# images = convert_from_path(PDF_file, 500,poppler_path=r'C:\Program Files\Poppler\poppler-0.68.0\bin')
# for i, image in enumerate(images):
#     fname = r'D:\Users\Simon\Python-VSCode\projects\ExamScanner\image'+str(i)+'.png'
#     image.save(fname, "PNG")

'''
Part #2 - Cropping the images
'''
imageFile = r'D:\Users\Simon\Python-VSCode\projects\ExamScanner\image0.png'
im = Image.open(imageFile)
# Size of the image in pixels (size of original image)
# (This is not mandatory)
width, height = im.size

print(width)
print(height)
# Setting the points for cropped image
left = 5
top = height / 4
right = 3500
bottom = 2000

# Cropped image of above dimension
# (It will not change original image)
im1 = im.crop((left, top, right, bottom))

# Shows the image in image viewer
im1.show()

