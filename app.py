import streamlit as st
from PIL import Image, ImageDraw
import numpy as np
from sklearn.cluster import KMeans
import io
import zipfile
import os
import base64

# Function to extract dominant colors
def extract_palette(image, num_colors=6):
    img = image.convert('RGB')
    data = np.array(img).reshape((-1, 3))
    kmeans = KMeans(n_clusters=num_colors, random_state=42).fit(data)
    return kmeans.cluster_centers_.astype(int)

# Drawing function

def draw_layout(image, colors, position, border_thickness, swatch_border_thickness, border_color, swatch_border_color, swatch_size, remove_adjacent_border):
    img_w, img_h = image.size
    border = border_thickness

    if position in ['top', 'bottom']:
        canvas = Image.new("RGB", (img_w + 2*border, img_h + swatch_size + 2*border), border_color)
    else:
        canvas = Image.new("RGB", (img_w + swatch_size + 2*border, img_h + 2*border), border_color)

    image_position = {
        'top': (border, swatch_size + border),
        'bottom': (border, border),
        'left': (swatch_size + border, border),
        'right': (border, border),
    }
    canvas.paste(image, image_position[position])

    draw = ImageDraw.Draw(canvas)
    if position in ['top', 'bottom']:
        swatch_width = image.width // len(colors)
        y_offset = border if position == 'top' else border + image.height
        for i, color in enumerate(colors):
            x0 = border + i * swatch_width
            x1 = border + (i + 1) * swatch_width
            y0 = y_offset - swatch_size if position == 'top' else y_offset
            y1 = y0 + swatch_size
            draw.rectangle([x0, y0, x1, y1], fill=tuple(color))
            if not remove_adjacent_border or i != 0:
                draw.line([(x0, y0), (x0, y1)], fill=swatch_border_color, width=swatch_border_thickness)
            if not remove_adjacent_border or i != len(colors)-1:
                draw.line([(x1, y0), (x1, y1)], fill=swatch_border_color, width=swatch_border_thickness)
            if not remove_adjacent_border or position == 'bottom':
                draw.line([(x0, y0), (x1, y0)], fill=swatch_border_color, width=swatch_border_thickness)
            if not remove_adjacent_border or position == 'top':
                draw.line([(x0, y1), (x1, y1)], fill=swatch_border_color, width=swatch_border_thickness)
    else:
        swatch_height = image.height // len(colors)
        x_offset = border if position == 'left' else border + image.width
        for i, color in enumerate(colors):
            y0 = border + i * swatch_height
            y1 = border + (i + 1) * swatch_height
            x0 = x_offset - swatch_size if position == 'left' else x_offset
            x1 = x0 + swatch_size
            draw.rectangle([x0, y0, x1, y1], fill=tuple(color))
            if not remove_adjacent_border or i != 0:
                draw.line([(x0, y0), (x1, y0)], fill=swatch_border_color, width=swatch_border_thickness)
            if not remove_adjacent_border or i != len(colors)-1:
                draw.line([(x0, y1), (x1, y1)], fill=swatch_border_color, width=swatch_border_thickness)
            if not remove_adjacent_border or position == 'right':
                draw.line([(x0, y0), (x0, y1)], fill=swatch_border_color, width=swatch_border_thickness)
            if not remove_adjacent_border or position == 'left':
                draw.line([(x1, y0), (x1, y1)], fill=swatch_border_color, width=swatch_border_thickness)

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

num_colors = st.slider("Number of swatches (dominant colors)", min_value=2, max_value=12, value=6)
swatch_size = st.slider("Swatch size (px)", min_value=20, max_value=200, value=100)
border_thickness = st.slider("Border thickness (in % of image width)", min_value=1, max_value=10, value=5)
swatch_border_thickness = st.slider("Swatch border thickness (in px)", min_value=0, max_value=10, value=5)
border_color = st.color_picker("Image border color", value="#FFFFFF")
swatch_border_color = st.color_picker("Swatch border color", value="#FFFFFF")
remove_adjacent_border = st.checkbox("Align swatches with image", value=True)

if uploaded_files and positions:
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED) as zipf:
        preview_html_blocks = []

        for uploaded_file in uploaded_files:
            image = Image.open(uploaded_file).convert("RGB")
            palette = extract_palette(image, num_colors)
            border_px = int(image.width * (border_thickness / 100))

            for pos in positions:
                result_img = draw_layout(image, palette, pos, border_px, swatch_border_thickness, border_color, swatch_border_color, swatch_size, remove_adjacent_border)
                img_byte_arr = io.BytesIO()
                name = f"{uploaded_file.name.rsplit('.', 1)[0]}_{pos}.jpg"
                result_img.save(img_byte_arr, format='JPEG', quality=95)
                zipf.writestr(name, img_byte_arr.getvalue())

                # Generate preview thumbnail
                result_img.thumbnail((200, 200))
                with io.BytesIO() as buffer:
                    result_img.save(buffer, format="PNG")
                    img_base64 = base64.b64encode(buffer.getvalue()).decode("utf-8")

                block = f"<div style='flex: 0 0 auto; text-align: center; width: 200px; box-shadow: 0 4px 12px rgba(0,0,0,0.2); padding: 8px; border-radius: 8px; background: #eeeeee;'>"
                block += f"<div style='font-size: 12px; margin-bottom: 5px;'>{name}</div>"
                block += f"<img src='data:image/png;base64,{img_base64}' width='200'>"
                block += "</div>"
                preview_html_blocks.append(block)

    zip_buffer.seek(0)
    st.download_button(
        label="📦 Download all as ZIP",
        data=zip_buffer,
        file_name="swatches.zip",
        mime="application/zip"
    )

    st.markdown("### Preview")
    full_html = "<div style='display: flex; overflow-x: auto; gap: 20px; padding: 10px;'>"
    full_html += "\n".join(preview_html_blocks)
    full_html += "</div>"
    st.markdown(full_html, unsafe_allow_html=True)
