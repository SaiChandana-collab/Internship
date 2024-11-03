# -*- coding: utf-8 -*-
"""Streamlit.ipynb

Automatically generated by Colab.

Original file is located at
    https://colab.research.google.com/drive/1zJonPG1q2mOLFnbdzp9PimhBLhn-FqWx
"""
import os

aws_access_key_id = os.getenv('AWS_ACCESS_KEY_ID')
aws_secret_access_key = os.getenv('AWS_SECRET_ACCESS_KEY')
aws_region = os.getenv('AWS_DEFAULT_REGION')


import streamlit as st
from PIL import Image
import pytesseract
import numpy as np
from sklearn.decomposition import PCA
import cv2
import boto3
import io


background_color = "#F0F2F5"
st.markdown(f"""
<style>
    body {{
        background-color: {background_color};
    }}
</style>
""", unsafe_allow_html=True)

def extract_text(image_bytes):
    # Create a Textract client
    client = boto3.client('textract', 
                           aws_access_key_id=aws_access_key_id,
                           aws_secret_access_key=aws_secret_access_key,
                           region_name=aws_region)
    
    # Call Textract
    response = client.detect_document_text(Document={'Bytes': image_bytes})
    
    # Extract text from the response
    text = ''
    for item in response['Blocks']:
        if item['BlockType'] == 'LINE':
            text += item['Text'] + '\n'
    
    return text
    
def denoise_approach_3(image):

    # Apply Bilateral Filtering
    image = cv2.fastNlMeansDenoising(image, None, h=10, templateWindowSize=7, searchWindowSize=41)
    denoised_image = cv2.bilateralFilter(image, d=15, sigmaColor=75, sigmaSpace=75)
    denoised_image = cv2.adaptiveThreshold(denoised_image.astype(np.uint8), 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 19)
    return denoised_image

def pca_denoising(image, variance_retained=0.95):
    # Convert image to float32 for PCA
    image_float32 = np.float32(image)

    # Flatten the image into a 1D array
    X = image_float32.flatten()

    # Perform PCA on the flattened image
    pca = PCA(n_components=variance_retained)
    pca.fit(X.reshape(-1, 1))

    # Project the noisy image onto the principal components
    projected_image = pca.transform(X.reshape(-1, 1))

    # Reconstruct the image using the reduced number of principal components
    reconstructed_image = pca.inverse_transform(projected_image).reshape(image.shape)

    # Convert reconstructed image back to uint8
    denoised_image = np.uint8(np.clip(reconstructed_image, 0, 255))

    return denoised_image

def denoise_approach_2(image):

    blurred_image = cv2.GaussianBlur(image, (1, 1), 0)

    # Step 2: Apply PCA Denoising
    blurred_image = cv2.fastNlMeansDenoising(blurred_image, None, 10, 17, 60)
    variance_retained = 0.15
    pca_denoised_image = pca_denoising(blurred_image, variance_retained)

    #_, final_denoised_image = cv2.threshold(pca_denoised_image, 127, 255, cv2.THRESH_BINARY)
    final_denoised_image = cv2.adaptiveThreshold(pca_denoised_image.astype(np.uint8), 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 17)
    return final_denoised_image

# Function to denoise image using Approach 1
def denoise_approach_1(image):
    scale_factor = 2
    org_image = cv2.resize(image, (0, 0), fx=scale_factor, fy=scale_factor)

    # Apply Non-Local Means Denoising
    if len(org_image.shape) == 3 and org_image.shape[2] == 3:
      org_image = cv2.cvtColor(org_image, cv2.COLOR_RGB2GRAY)  # Convert to grayscale if not already
    image = cv2.fastNlMeansDenoising(org_image, None, h=10, templateWindowSize=15, searchWindowSize=71)

    # Apply anisotropic diffusion
    denoised_image = anisotropic_diffusion(image, iterations=30, kappa=20, gamma=0.2, option=1)

    # Apply adaptive thresholding
    denoised_image = cv2.adaptiveThreshold(denoised_image.astype(np.uint8), 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 29)

    return denoised_image

def anisotropic_diffusion(image, iterations, kappa, gamma, option):
    image = image.astype('float32')

    if option == 1:
        image = cv2.GaussianBlur(image, (1, 1), 0)
    elif option == 2:
        image = cv2.medianBlur(image.astype(np.uint8), 3)

    # Pad the image to handle border cases
    image_padded = np.pad(image, ((1, 1), (1, 1)), mode='constant')

    for i in range(iterations):
        # Compute gradients
        nablaN = image_padded[:-2, 1:-1] - image_padded[1:-1, 1:-1]
        nablaS = image_padded[2:, 1:-1] - image_padded[1:-1, 1:-1]
        nablaW = image_padded[1:-1, :-2] - image_padded[1:-1, 1:-1]
        nablaE = image_padded[1:-1, 2:] - image_padded[1:-1, 1:-1]

        # Conductance
        cN = np.exp(-(nablaN / kappa) ** 2)
        cS = np.exp(-(nablaS / kappa) ** 2)
        cW = np.exp(-(nablaW / kappa) ** 2)
        cE = np.exp(-(nablaE / kappa) ** 2)

        # Update image
        image_update = image_padded[1:-1, 1:-1] + gamma * (
            cN * nablaN + cS * nablaS + cW * nablaW + cE * nablaE
        )

        # Update padded image
        image_padded[1:-1, 1:-1] = image_update

    return image_padded[1:-1, 1:-1]


def extract_text_from_image(image):
    return pytesseract.image_to_string(image, lang='eng',config=r'--oem 3 --psm 6')

# Main function to run the Streamlit app
def main():
    st.title("Image Denoising App")
    st.write("Upload your noisy image and choose the best denoising approach.")

    # Upload image
    uploaded_image = st.file_uploader("Upload", type=["jpg", "png", "jpeg", "tif"], accept_multiple_files=False)

    if uploaded_image is not None:
        # Display uploaded image
        image = Image.open(uploaded_image)
        original_height = 200
        denoised_height = 400
        image_np = np.array(image)

        # Calculate the aspect ratio
        aspect_ratio = image_np.shape[1] / image_np.shape[0]

        # Calculate the widths for the new heights
        original_width = int(original_height * aspect_ratio)
        denoised_width = int(denoised_height * aspect_ratio)
        st.image(image, caption='Uploaded Image', use_column_width=True,width=original_width)

        # Apply denoising approaches
        denoised_image_1 = denoise_approach_1(image_np)
        denoised_image_2 = denoise_approach_2(image_np)
        denoised_image_3 = denoise_approach_3(image_np)

        col1, col2, col3 = st.columns([5,5,5])
        with col1:
            st.image(denoised_image_1, caption='Anisotropic Diffusion', use_column_width=True, clamp=True, channels="GRAY", width=denoised_width)
            if st.button('Anisotropic OCR'):
                
                with io.BytesIO() as buffer:
                   denoised_image_1.save(buffer, format='PNG')  # Save as PNG or JPG
                   image_bytes = buffer.getvalue()
# Extract text from image
                extracted_text = extract_text(image_bytes)
                st.subheader("Extracted Text:")
                st.write(extracted_text)
                extracted_text = extract_text_from_image(denoised_image_1)
                st.text_area('Extracted Text', extracted_text, height=500)

        with col2:
            st.image(denoised_image_2, caption='PCA ', use_column_width=True, clamp=True, channels="GRAY", width=denoised_width)
            if st.button('PCA OCR'):
                extracted_text = extract_text_from_image(denoised_image_2)
                st.text_area('Extracted Text', extracted_text, height=500)

        with col3:
            st.image(denoised_image_3, caption='Bilateral Filtering', use_column_width=True, clamp=True, channels="GRAY", width=denoised_width)
            if st.button('Bilateral Filtering OCR'):
                extracted_text = extract_text_from_image(denoised_image_3)
                st.text_area('Extracted Text', extracted_text, height=500)
# Run the app
if __name__ == '__main__':
    main()


