# Import libraries
from PIL import Image
import sys
from pdf2image import convert_from_path

# Path of the pdf
PDF_file = "d.pdf"

#Function definitions

'''
Part #1 : Converting PDF to images
Poppler is required by pdf2image. On Windows it is a pain to install. I downloaded a binary and added the poppler_path parameter to the call below.
'''
def convertToImages(pdfFile):
    images = convert_from_path(pdfFile, 500,poppler_path=r'C:\Program Files\Poppler\poppler-0.68.0\bin')
    for i, image in enumerate(images):
        fname = r'image'+str(i)+'.png'
        image.save(fname, "PNG")

'''
Part #2 - Cropping the images
'''
def cropImage(image,l,t,r,b):

    im = Image.open(imageFile)
    # Size of the image in pixels (size of original image)
    width, height = im.size
    # Setting the points for cropped image
    left = l
    top = t
    right = r
    bottom = b

    # Cropped image of above dimension (It will not change original image)
    im1 = im.crop((left, top, right, bottom))

    # Shows the image in image viewer
    im1.show()


#Main program (calls functions)
convertToImages(PDF_file)

imageFile = 'image0.png'
cropImage(imageFile,5,100,3500, 2000)
