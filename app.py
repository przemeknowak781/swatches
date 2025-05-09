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

    if position == 'top':
        canvas = Image.new("RGB", (img_w + 2 * border, img_h + swatch_size + 2 * border), border_color)
        canvas.paste(image, (border, swatch_size + border))
        swatch_y = border
        swatch_width = img_w // len(colors)
        for i, color in enumerate(colors):
            x0 = border + i * swatch_width
            x1 = border + (i + 1) * swatch_width
            y0 = swatch_y
            y1 = swatch_y + swatch_size
            draw = ImageDraw.Draw(canvas)
            draw.rectangle([x0, y0, x1, y1], fill=tuple(color))
            if not remove_adjacent_border or i != 0:
                draw.line([(x0, y0), (x0, y1)], fill=swatch_border_color, width=swatch_border_thickness)
            if not remove_adjacent_border or i != len(colors) - 1:
                draw.line([(x1, y0), (x1, y1)], fill=swatch_border_color, width=swatch_border_thickness)
            draw.line([(x0, y0), (x1, y0)], fill=swatch_border_color, width=swatch_border_thickness)
            draw.line([(x0, y1), (x1, y1)], fill=swatch_border_color, width=swatch_border_thickness)

    elif position == 'bottom':
        canvas = Image.new("RGB", (img_w + 2 * border, img_h + swatch_size + 2 * border), border_color)
        canvas.paste(image, (border, border))
        swatch_y = border + img_h
        swatch_width = img_w // len(colors)
        for i, color in enumerate(colors):
            x0 = border + i * swatch_width
            x1 = border + (i + 1) * swatch_width
            y0 = swatch_y
            y1 = swatch_y + swatch_size
            draw = ImageDraw.Draw(canvas)
            draw.rectangle([x0, y0, x1, y1], fill=tuple(color))
            if not remove_adjacent_border or i != 0:
                draw.line([(x0, y0), (x0, y1)], fill=swatch_border_color, width=swatch_border_thickness)
            if not remove_adjacent_border or i != len(colors) - 1:
                draw.line([(x1, y0), (x1, y1)], fill=swatch_border_color, width=swatch_border_thickness)
            draw.line([(x0, y0), (x1, y0)], fill=swatch_border_color, width=swatch_border_thickness)
            draw.line([(x0, y1), (x1, y1)], fill=swatch_border_color, width=swatch_border_thickness)

    elif position == 'left':
        canvas = Image.new("RGB", (img_w + swatch_size + 2 * border, img_h + 2 * border), border_color)
        canvas.paste(image, (swatch_size + border, border))
        swatch_x = border
        swatch_height = img_h // len(colors)
        for i, color in enumerate(colors):
            y0 = border + i * swatch_height
            y1 = border + (i + 1) * swatch_height
            x0 = swatch_x
            x1 = swatch_x + swatch_size
            draw = ImageDraw.Draw(canvas)
            draw.rectangle([x0, y0, x1, y1], fill=tuple(color))
            if not remove_adjacent_border or i != 0:
                draw.line([(x0, y0), (x1, y0)], fill=swatch_border_color, width=swatch_border_thickness)
            if not remove_adjacent_border or i != len(colors) - 1:
                draw.line([(x0, y1), (x1, y1)], fill=swatch_border_color, width=swatch_border_thickness)
            draw.line([(x0, y0), (x0, y1)], fill=swatch_border_color, width=swatch_border_thickness)
            draw.line([(x1, y0), (x1, y1)], fill=swatch_border_color, width=swatch_border_thickness)

    elif position == 'right':
        canvas = Image.new("RGB", (img_w + swatch_size + 2 * border, img_h + 2 * border), border_color)
        canvas.paste(image, (border, border))
        swatch_x = border + img_w
        swatch_height = img_h // len(colors)
        for i, color in enumerate(colors):
            y0 = border + i * swatch_height
            y1 = border + (i + 1) * swatch_height
            x0 = swatch_x
            x1 = swatch_x + swatch_size
            draw = ImageDraw.Draw(canvas)
            draw.rectangle([x0, y0, x1, y1], fill=tuple(color))
            if not remove_adjacent_border or i != 0:
                draw.line([(x0, y0), (x1, y0)], fill=swatch_border_color, width=swatch_border_thickness)
            if not remove_adjacent_border or i != len(colors) - 1:
                draw.line([(x0, y1), (x1, y1)], fill=swatch_border_color, width=swatch_border_thickness)
            draw.line([(x0, y0), (x0, y1)], fill=swatch_border_color, width=swatch_border_thickness)
            draw.line([(x1, y0), (x1, y1)], fill=swatch_border_color, width=swatch_border_thickness)

    return canvas

# Streamlit UI
st.set_page_config(layout="wide")
st.title("🎨 Color Swatch Generator")

st.markdown("""
    <style>
    @media (min-width: 768px) {
        .responsive-columns {
            display: flex;
            gap: 2rem;
        }
        .responsive-columns > div {
            flex: 1;
        }
    }
    </style>
""", unsafe_allow_html=True)

zip_buffer = None
preview_container = st.container()
preview_html_blocks = []

st.markdown('<div class="responsive-columns">', unsafe_allow_html=True)

col1, col2, col3 = st.columns(3)

with col1:
    st.subheader("Upload Images")
    uploaded_files = st.file_uploader("Upload images", type=["jpg", "jpeg", "png"], accept_multiple_files=True)

with col2:
    st.subheader("Layout Settings")
    positions = st.multiselect("Swatch position(s)", ["top", "bottom", "left", "right"], default=["bottom"])
    num_colors = st.slider("Number of swatches", min_value=2, max_value=12, value=6)
    swatch_size = st.slider("Swatch size (px)", min_value=20, max_value=200, value=100)

with col3:
    st.subheader("Borders")
    border_thickness = st.slider("Image border thickness (% of image width)", min_value=0, max_value=10, value=0)
    border_color = st.color_picker("Image border color", value="#FFFFFF")
    swatch_border_thickness = st.slider("Swatch border thickness (px)", min_value=0, max_value=50, value=5)
    swatch_border_color = st.color_picker("Swatch border color", value="#FFFFFF")
    remove_adjacent_border = st.checkbox("Align swatches with image", value=True)

st.markdown('</div>', unsafe_allow_html=True)

if uploaded_files and positions:
    with st.spinner("Generating previews, please wait..."):
        zip_buffer = io.BytesIO()
        preview_html_blocks = []
        with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED) as zipf:
            for uploaded_file in uploaded_files:
                image = Image.open(uploaded_file).convert("RGB")
                palette = extract_palette(image, num_colors)
                border_px = int(image.width * (border_thickness / 100))

                for pos in positions:
                    result_img = draw_layout(
                        image, palette, pos, border_px, swatch_border_thickness,
                        border_color, swatch_border_color, swatch_size, remove_adjacent_border
                    )
                    img_byte_arr = io.BytesIO()
                    name = f"{uploaded_file.name.rsplit('.', 1)[0]}_{pos}.jpg"
                    result_img.save(img_byte_arr, format='JPEG', quality=95)
                    zipf.writestr(name, img_byte_arr.getvalue())

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

if preview_html_blocks:
    with preview_container:
        st.markdown("### Preview")
        full_html = "<div style='display: flex; overflow-x: auto; gap: 20px; padding: 10px;'>" + "
".join(preview_html_blocks) + "</div>"
        st.markdown(full_html, unsafe_allow_html=True)
        st.download_button("📦 Download all as ZIP", zip_buffer, file_name="swatches.zip", mime="application/zip")"📦 Download all as ZIP", zip_buffer, file_name="swatches.zip", mime="application/zip")
