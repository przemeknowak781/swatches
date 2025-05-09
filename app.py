import streamlit as st
from PIL import Image, ImageDraw
import numpy as np
from sklearn.cluster import KMeans
import io
import zipfile
import os

# SETTINGS
NUM_COLORS = 6
SWATCH_THICKNESS = 100

# Function to extract dominant colors
def extract_palette(image, num_colors=6):
    img = image.convert('RGB')
    data = np.array(img).reshape((-1, 3))
    kmeans = KMeans(n_clusters=num_colors, random_state=42).fit(data)
    return kmeans.cluster_centers_.astype(int)

# Drawing function
def draw_layout(image, colors, position, border_thickness):
    img_w, img_h = image.size
    border = border_thickness

    if position in ['top', 'bottom']:
        canvas = Image.new("RGB", (img_w + 2*border, img_h + SWATCH_THICKNESS + 2*border), "white")
    else:
        canvas = Image.new("RGB", (img_w + SWATCH_THICKNESS + 2*border, img_h + 2*border), "white")

    if position == 'top':
        canvas.paste(image, (border, SWATCH_THICKNESS + border))
        swatch_area = (border, border, img_w + border, SWATCH_THICKNESS + border)
    elif position == 'bottom':
        canvas.paste(image, (border, border))
        swatch_area = (border, img_h + border, img_w + border, img_h + SWATCH_THICKNESS + border)
    elif position == 'left':
        canvas.paste(image, (SWATCH_THICKNESS + border, border))
        swatch_area = (border, border, SWATCH_THICKNESS + border, img_h + border)
    elif position == 'right':
        canvas.paste(image, (border, border))
        swatch_area = (img_w + border, border, img_w + SWATCH_THICKNESS + border, img_h + border)

    draw = ImageDraw.Draw(canvas)
    swatch_border = max(1, border // 10)  # border around each swatch
    if position in ['top', 'bottom']:
        swatch_width = image.width // NUM_COLORS
        for i, color in enumerate(colors):
            x0 = swatch_area[0] + i * swatch_width
            draw.rectangle([x0, swatch_area[1], x0 + swatch_width, swatch_area[3]], fill=tuple(color))
            draw.rectangle([x0, swatch_area[1], x0 + swatch_width, swatch_area[3]], outline="black", width=swatch_border)
    else:
        swatch_height = image.height // NUM_COLORS
        for i, color in enumerate(colors):
            y0 = swatch_area[1] + i * swatch_height
            draw.rectangle([swatch_area[0], y0, swatch_area[2], y0 + swatch_height], fill=tuple(color))
            draw.rectangle([swatch_area[0], y0, swatch_area[2], y0 + swatch_height], outline="black", width=swatch_border)

    return canvas

# Streamlit UI
st.set_page_config(layout="wide")
st.title("🎨 Color Swatch Generator")

uploaded_files = st.file_uploader("Upload one or more images", type=["jpg", "jpeg", "png"], accept_multiple_files=True)

positions = st.multiselect(
    "Choose swatch position(s)",
    options=["top", "bottom", "left", "right"],
    default=["bottom"]
)

border_thickness = st.slider("Border thickness (in % of image width)", min_value=1, max_value=10, value=2)

if uploaded_files and positions:
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED) as zipf:
        preview_imgs = []

        for uploaded_file in uploaded_files:
            image = Image.open(uploaded_file).convert("RGB")
            palette = extract_palette(image, NUM_COLORS)
            border_px = int(image.width * (border_thickness / 100))

            for pos in positions:
                result_img = draw_layout(image, palette, pos, border_px)
                img_byte_arr = io.BytesIO()
                name = f"{uploaded_file.name.rsplit('.', 1)[0]}_{pos}.jpg"
                result_img.save(img_byte_arr, format='JPEG', quality=95)
                zipf.writestr(name, img_byte_arr.getvalue())

                preview_imgs.append((name, result_img))

    zip_buffer.seek(0)
    st.download_button(
        label="📦 Download all as ZIP",
        data=zip_buffer,
        file_name="swatches.zip",
        mime="application/zip"
    )

    st.markdown("### Preview")
    with st.container():
        st.markdown("<div style='display: flex; overflow-x: auto;'>", unsafe_allow_html=True)
        for name, img in preview_imgs:
            with st.container():
                st.markdown(f"<div style='margin-right: 20px; text-align: center; width: 200px;'>", unsafe_allow_html=True)
                st.caption(name)
                st.image(img, use_container_width=True, clamp=True)
                st.markdown("</div>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)
